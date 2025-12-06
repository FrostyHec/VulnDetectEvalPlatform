import os
import torch
import logging
import argparse
import glob
from dataclasses import asdict
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from torch.optim import AdamW
from ignite.engine import Engine, Events
from ignite.handlers import ModelCheckpoint, Checkpoint
from ignite.metrics import RunningAverage
from ignite.contrib.handlers import ProgressBar

from src.adapted_tools.primeVul.config import Config, get_config
from src.adapted_tools.primeVul.common import get_dataloader
from src.adapted_tools.primeVul.model import Model, DefectModel
from src.common.eval.evaluation import calculate_metrics, calculate_pairwise_metrics

def setup_logging(output_dir):
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s -   %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
        handlers=[
            logging.FileHandler(os.path.join(output_dir, "train.log")),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def train(config: Config, resume_from: str = None, load_pretrained: str = None):
    logger = setup_logging(config.output_dir)
    logger.info(f"Configuration: {asdict(config)}")
    
    # Set seed
    torch.manual_seed(config.seed)
    if config.n_gpu > 0:
        torch.cuda.manual_seed_all(config.seed)
        
    # Tokenizer & Model
    logger.info(f"Loading model: {config.model_name_or_path}")
    tokenizer = AutoTokenizer.from_pretrained(config.model_name_or_path)
    
    if config.model_type in ['codet5', 't5']:
        from transformers import T5ForConditionalGeneration
        base_model = T5ForConditionalGeneration.from_pretrained(config.model_name_or_path)
        model = DefectModel(base_model, base_model.config, tokenizer, config)
    else:
        base_model = AutoModelForSequenceClassification.from_pretrained(config.model_name_or_path, num_labels=2)
        model = Model(base_model, config, tokenizer, config) # Pass config as args
        
    model.to(config.device)
    
    # Load pretrained weights if specified (and not resuming, as resume handles it)
    if load_pretrained and not resume_from:
        logger.info(f"Loading pretrained weights from {load_pretrained}")
        ck = torch.load(load_pretrained, map_location=config.device)
        # Support multiple checkpoint formats: ignite checkpoint (dict with 'model'), plain state_dict, or saved model
        try:
            if isinstance(ck, dict) and 'model' in ck:
                mobj = ck['model']
                if isinstance(mobj, dict):
                    model.load_state_dict(mobj)
                elif hasattr(mobj, 'state_dict'):
                    model.load_state_dict(mobj.state_dict())
                else:
                    # fallback: try to load ck directly
                    model.load_state_dict(ck)
            elif isinstance(ck, dict) and all(isinstance(v, torch.Tensor) for v in ck.values()):
                # looks like a state_dict
                model.load_state_dict(ck)
            elif hasattr(ck, 'state_dict'):
                model.load_state_dict(ck.state_dict())
            else:
                model.load_state_dict(ck)
        except Exception as e:
            logger.error(f"Failed to load pretrained weights: {e}")
            raise

    # Data Loaders
    logger.info("Loading datasets...")
    train_loader = get_dataloader(config.train_file, tokenizer, config.train_batch_size, config.max_len, shuffle=True, split='train', my_primevul_format=config.my_primevul_format)
    valid_loader = get_dataloader(config.valid_file, tokenizer, config.eval_batch_size, config.max_len, shuffle=False, split='val', my_primevul_format=config.my_primevul_format)
    # test_loader = get_dataloader(config.test_file, tokenizer, config.eval_batch_size, config.max_len, shuffle=False, split='test', my_primevul_format=config.my_primevul_format)
    
    # Optimizer & Scheduler
    no_decay = ['bias', 'LayerNorm.weight']
    optimizer_grouped_parameters = [
        {'params': [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)], 'weight_decay': config.weight_decay},
        {'params': [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
    ]
    optimizer = AdamW(optimizer_grouped_parameters, lr=config.learning_rate, eps=config.adam_epsilon)
    
    t_total = len(train_loader) * config.num_train_epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=t_total)
    
    # Training Step
    def train_step(engine, batch):
        model.train()
        batch = {k: v.to(config.device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
        
        loss, prob = model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'], labels=batch['label'])
        
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
        
        if (engine.state.iteration % config.gradient_accumulation_steps) == 0:
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
        
        return loss.item()

    trainer = Engine(train_step)
    
    # Evaluation Step
    def validation_step(engine, batch):
        model.eval()
        with torch.no_grad():
            batch = {k: v.to(config.device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
            loss, prob = model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'], labels=batch['label'])
            
            # Convert probabilities to predictions
            if config.model_type in ['codet5', 't5']:
                # For CodeT5, prob is softmax output, prob[:, 1] is probability of Vulnerable (Label 1)
                preds = (prob[:, 1] > 0.5).long()
            else:
                # For CodeBERT/UnixCoder (Model class), prob is sigmoid of logits
                # prob[:, 0] is the probability of label 1 (Vulnerable) in the original PrimeVul model
                preds = (prob[:, 0] > 0.5).long()
            
            return preds, batch['label'], batch['id']

    evaluator = Engine(validation_step)
    
    # Metrics
    RunningAverage(output_transform=lambda x: x).attach(trainer, 'loss')
    
    @evaluator.on(Events.STARTED)
    def reset_results(engine):
        engine.state.all_preds = []
        engine.state.all_labels = []
        engine.state.all_ids = []

    @evaluator.on(Events.ITERATION_COMPLETED)
    def accumulate_results(engine):
        preds, labels, ids = engine.state.output
        engine.state.all_preds.extend(preds.cpu().tolist())
        engine.state.all_labels.extend(labels.cpu().tolist())
        engine.state.all_ids.extend(ids)

    @evaluator.on(Events.COMPLETED)
    def compute_metrics(engine):
        metrics = calculate_metrics(engine.state.all_labels, engine.state.all_preds)
        
        # Prepare results for pairwise
        results_for_pairwise = []
        for i in range(len(engine.state.all_ids)):
            results_for_pairwise.append({
                'id': engine.state.all_ids[i],
                'label': engine.state.all_labels[i],
                'pred': engine.state.all_preds[i]
            })
        
        pairwise_metrics = calculate_pairwise_metrics(results_for_pairwise)
        
        logger.info(f"Validation Results - Epoch {trainer.state.epoch}")
        logger.info(f"Metrics: {metrics}")
        logger.info(f"Pairwise Metrics: {pairwise_metrics}")
        
        # Store metrics in state for checkpointing or early stopping if needed
        engine.state.metrics = metrics

    @trainer.on(Events.EPOCH_COMPLETED)
    def log_training_results(engine):
        logger.info(f"Epoch {engine.state.epoch} - Loss: {engine.state.metrics['loss']:.4f}")

    @trainer.on(Events.EPOCH_COMPLETED)
    def run_validation(engine):
        evaluator.run(valid_loader)

    # Checkpointing - Current Model (Last 2 epochs)
    # We save model, optimizer, scheduler, and trainer (for epoch/iteration)
    to_save = {'model': model, 'optimizer': optimizer, 'scheduler': scheduler, 'trainer': trainer}
    checkpoint_handler = ModelCheckpoint(config.output_dir, 'checkpoint', n_saved=2, require_empty=False)
    trainer.add_event_handler(Events.EPOCH_COMPLETED, checkpoint_handler, to_save)
    
    # Checkpointing - Best Model (based on F1 score)
    def score_function(engine):
        return engine.state.metrics['f1']
        
    best_model_handler = ModelCheckpoint(
        config.output_dir, 
        'best_model', 
        n_saved=1, 
        require_empty=False, 
        score_name="f1", 
        score_function=score_function
    )
    evaluator.add_event_handler(Events.COMPLETED, best_model_handler, {'model': model})
    
    # Resume logic
    if resume_from:
        logger.info(f"Resuming training from checkpoint: {resume_from}")
        checkpoint = torch.load(resume_from, map_location=config.device)
        Checkpoint.load_objects(to_load=to_save, checkpoint=checkpoint)

    # Progress Bar
    pbar = ProgressBar()
    pbar.attach(trainer, output_transform=lambda x: {'loss': x})
    
    logger.info("Starting training...")
    trainer.run(train_loader, max_epochs=config.num_train_epochs)

def main():
    parser = argparse.ArgumentParser()
    
    # Config selection
    parser.add_argument("--model_config", type=str, default="codebert", help="Model config name (codebert, unixcoder, codet5)")
    parser.add_argument("--exp_name", type=str, default=None, help="Experiment name (creates output/dataset_patch/primevul/<exp_name>)")
    parser.add_argument("--output_dir", type=str, default=None, help="Explicit output directory override")
    
    # Training control
    parser.add_argument("--continue_train", action="store_true", help="Resume training from latest checkpoint in output_dir")
    parser.add_argument("--load_pretrained", type=str, default=None, help="Path to pretrained model weights to load")
    parser.add_argument("--gpu", type=int, default=None, help="GPU id to run on (e.g. 0). If not set, use CPU or default device in config.")
    parser.add_argument("--my_primevul_format", action="store_true", help="Use custom PrimeVul format (ds.jsonl + index_split.csv)")
    
    # Config overrides
    parser.add_argument("--num_train_epochs", type=int, help="Override num_train_epochs")
    parser.add_argument("--learning_rate", type=float, help="Override learning_rate")
    parser.add_argument("--train_batch_size", type=int, help="Override train_batch_size")
    parser.add_argument("--eval_batch_size", type=int, help="Override eval_batch_size")
    
    args = parser.parse_args()
    
    # Collect overrides
    overrides = {k: v for k, v in vars(args).items() if v is not None and k in Config.__annotations__}
    # If my_primevul_format is False (default from argparse), remove it so we don't override the preset's True
    if 'my_primevul_format' in overrides and not overrides['my_primevul_format']:
        del overrides['my_primevul_format']
    
    # Get config
    config = get_config(
        model_name=args.model_config,
        exp_name=args.exp_name,
        output_dir=args.output_dir,
        **overrides
    )

    # GPU selection: if user passed --gpu, set device accordingly
    if args.gpu is not None:
        if args.gpu < 0:
            config.device = torch.device("cpu")
            config.n_gpu = 0
        else:
            if torch.cuda.is_available():
                # check that the requested GPU index is valid
                if args.gpu >= torch.cuda.device_count():
                    raise ValueError(f"Requested GPU id {args.gpu} is out of range (found {torch.cuda.device_count()} GPUs).")
                config.device = torch.device(f"cuda:{args.gpu}")
                # set visible GPU count to 1 (we target a single device selection)
                config.n_gpu = 1
            else:
                raise RuntimeError("CUDA is not available but --gpu was provided. Either run on a machine with CUDA or omit --gpu.")

    
    # Check output directory safety
    if os.path.exists(config.output_dir) and os.listdir(config.output_dir):
        if not args.continue_train:
            # Check if it's just logs or empty folders, maybe? 
            # User requirement: "If not passed but folder has things, error"
            # We'll be strict.
            raise ValueError(f"Output directory {config.output_dir} is not empty. Use --continue_train to resume or clear the directory.")
    
    # Determine resume path if continue_train is set
    resume_path = None
    if args.continue_train:
        # Find latest checkpoint: accept any .pt file and prefer those with 'checkpoint' in the name
        all_ckpts = glob.glob(os.path.join(config.output_dir, "*.pt"))
        if not all_ckpts:
            print(f"No checkpoint found in {config.output_dir}, starting from scratch.")
        else:
            # prefer files that contain 'checkpoint' in the filename
            ckpts_pref = [p for p in all_ckpts if 'checkpoint' in os.path.basename(p)]
            candidates = ckpts_pref if ckpts_pref else all_ckpts
            resume_path = max(candidates, key=os.path.getmtime)
            
    train(config, resume_from=resume_path, load_pretrained=args.load_pretrained)

if __name__ == "__main__":
    main()
