import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Optional

def detect_jdk_version_maven(pom_path: str) -> (int, Optional[str]):
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        # Namespace handling
        ns = {}
        if '}' in root.tag:
            ns = {'mvn': root.tag.split('}')[0].strip('{')}

        # Helper to find with namespace
        def find_text(node, path):
            if ns:
                # Replace /tag with /mvn:tag
                path = '/'.join(f"mvn:{p}" for p in path.split('/'))
            return node.findtext(path, namespaces=ns)

        # Check properties
        properties = root.find('mvn:properties', namespaces=ns) if ns else root.find('properties')
        if properties is not None:
            java_ver = properties.findtext('mvn:java.version', namespaces=ns) if ns else properties.findtext('java.version')
            if java_ver:
                return parse_java_version(java_ver), "java.version"
            
            # Check jdk.version
            jdk_ver = properties.findtext('mvn:jdk.version', namespaces=ns) if ns else properties.findtext('jdk.version')
            if jdk_ver:
                return parse_java_version(jdk_ver), "jdk.version"

            compiler_source = properties.findtext('mvn:maven.compiler.source', namespaces=ns) if ns else properties.findtext('maven.compiler.source')
            if compiler_source:
                return parse_java_version(compiler_source), "maven.compiler.source"

        # Check plugins (maven-compiler-plugin) - simplified check
        # This is harder with XML parsing without full traversal, skipping for now as properties cover most.
        
    except Exception as e:
        print(f"Error parsing pom.xml: {e}")
    
    return 8, None # Default

def detect_jdk_version_gradle(gradle_path: str) -> int:
    try:
        with open(gradle_path, 'r') as f:
            content = f.read()
            # sourceCompatibility = 1.8 or '1.8' or JavaVersion.VERSION_1_8
            match = re.search(r"sourceCompatibility\s*=\s*['\"]?([0-9.]+|_?[A-Z0-9_]+)['\"]?", content)
            if match:
                return parse_java_version(match.group(1))
    except Exception as e:
        print(f"Error parsing build.gradle: {e}")
    return 8

def parse_java_version(ver_str: str) -> int:
    ver_str = str(ver_str).lower().replace('version_', '').replace('java_', '')
    if ver_str.startswith('1.'):
        return int(ver_str.split('.')[1])
    elif '.' in ver_str:
        return int(ver_str.split('.')[0])
    try:
        return int(ver_str)
    except:
        return 8

def generate_build_info(project_path: str) -> Dict[str, str]:
    pom_path = os.path.join(project_path, 'pom.xml')
    gradle_path = os.path.join(project_path, 'build.gradle')
    
    info = {
        "build_system": "unknown",
        "jdk_version": "8",
        "build_command": "",
        "status": "success" # Optimistic
    }

    if os.path.exists(pom_path):
        info["build_system"] = "maven"
        ver, prop_name = detect_jdk_version_maven(pom_path)
        info["jdk_version"] = str(ver)
        
        cmd = "mvn clean package -Dmaven.test.skip=true -B"
        
        if ver < 8:
            # Force upgrade to 1.8 for JDK 21 compatibility
            if prop_name:
                cmd += f" -D{prop_name}=1.8"
            cmd += " -Dmaven.compiler.source=1.8 -Dmaven.compiler.target=1.8"
            
        info["build_command"] = cmd
    elif os.path.exists(gradle_path):
        info["build_system"] = "gradle"
        info["jdk_version"] = str(detect_jdk_version_gradle(gradle_path))
        # Check for gradlew
        if os.path.exists(os.path.join(project_path, 'gradlew')):
            info["build_command"] = "./gradlew clean build -x test"
        else:
            info["build_command"] = "gradle clean build -x test"
    else:
        info["status"] = "failed"
        info["error"] = "No build file found"
        
    return info

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(generate_build_info(sys.argv[1]))
