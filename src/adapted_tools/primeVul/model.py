# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
import torch
import torch.nn as nn
import torch
from torch.autograd import Variable
import copy
from torch.nn import CrossEntropyLoss, MSELoss
from transformers.models.roberta.modeling_roberta import RobertaClassificationHead
import torch.nn.functional as F
    
    
class Model(nn.Module):   
    def __init__(self, encoder, config, tokenizer, args):
        super(Model, self).__init__()
        self.encoder = encoder
        self.config=config
        self.tokenizer=tokenizer
        self.args=args
    
        
    def forward(self, input_ids=None, attention_mask=None, labels=None, weight=None): 
        if attention_mask is None:
            attention_mask = input_ids.ne(self.tokenizer.pad_token_id)
        outputs=self.encoder(input_ids,attention_mask=attention_mask)[0]
        logits=outputs
        prob=torch.sigmoid(logits)
        if weight is not None:
            weight = torch.tensor(weight, device=prob.device)
        if labels is not None:
            labels=labels.float()
            if weight == None:
                loss=torch.log(prob[:,0]+1e-10)*labels+torch.log((1-prob)[:,0]+1e-10)*(1-labels)
            else:
                loss=torch.log(prob[:,0]+1e-10)*labels*weight[1]+torch.log((1-prob)[:,0]+1e-10)*(1-labels)*weight[0]
            loss=-loss.mean()
            return loss,prob
        else:
            return prob

class DefectModel(nn.Module):
    def __init__(self, encoder, config, tokenizer, args):
        super(DefectModel, self).__init__()
        self.encoder = encoder
        self.config = config
        self.tokenizer = tokenizer
        self.classifier = nn.Linear(config.hidden_size, 2)
        self.args = args

    def get_t5_vec(self, source_ids):
        attention_mask = source_ids.ne(self.tokenizer.pad_token_id)
        outputs = self.encoder(input_ids=source_ids, attention_mask=attention_mask,
                               labels=source_ids, decoder_attention_mask=attention_mask, output_hidden_states=True)
        hidden_states = outputs['decoder_hidden_states'][-1]
        eos_mask = source_ids.eq(self.config.eos_token_id)

        if len(torch.unique(eos_mask.sum(1))) > 1:
            print(eos_mask.sum(1))
            print(torch.unique(eos_mask.sum(1)))
            raise ValueError("All examples must have the same number of <eos> tokens.")
        vec = hidden_states[eos_mask, :].view(hidden_states.size(0), -1,
                                              hidden_states.size(-1))[:, -1, :]
        return vec

    def get_bart_vec(self, source_ids):
        attention_mask = source_ids.ne(self.tokenizer.pad_token_id)
        outputs = self.encoder(input_ids=source_ids, attention_mask=attention_mask,
                               labels=source_ids, decoder_attention_mask=attention_mask, output_hidden_states=True)
        hidden_states = outputs['decoder_hidden_states'][-1]
        eos_mask = source_ids.eq(self.config.eos_token_id)

        if len(torch.unique(eos_mask.sum(1))) > 1:
            raise ValueError("All examples must have the same number of <eos> tokens.")
        vec = hidden_states[eos_mask, :].view(hidden_states.size(0), -1,
                                              hidden_states.size(-1))[:, -1, :]
        return vec

    def get_roberta_vec(self, source_ids):
        attention_mask = source_ids.ne(self.tokenizer.pad_token_id)
        vec = self.encoder(input_ids=source_ids, attention_mask=attention_mask)[0][:, 0, :]
        return vec

    def forward(self, input_ids=None, attention_mask=None, labels=None, weight=None):
        # source_ids = source_ids.view(-1, self.args.max_source_length)
        source_ids = input_ids

        if self.args.model_type == 'codet5':
            vec = self.get_t5_vec(source_ids)
        elif self.args.model_type == 'bart':
            vec = self.get_bart_vec(source_ids)
        elif self.args.model_type == 'roberta':
            vec = self.get_roberta_vec(source_ids)
        elif self.args.model_type == 't5':
            vec = self.get_t5_vec(source_ids)
        
        logits = self.classifier(vec)
        prob = nn.functional.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = nn.CrossEntropyLoss(weight=weight)
            loss = loss_fct(logits, labels)
            return loss, prob
        else:
            return prob
