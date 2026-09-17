#!/usr/bin/env python3
"""Inventory runnable first-party apps with executable UI/runtime entrypoints.

Determines which current Aetherius projects/apps actually have executable
UI/runtime entrypoints for human testing.
"""
import json
import os
from pathlib import Path

# Project directories
PROJECTS = {
    "AGENT_BRIDGE": r"C:\Users\jpowe\Desktop\Agent-Bridge",
    "IDE_WORKSPACE": r"C:\Users\jpowe\Desktop\IDE-Workspace",
    "GENESIS": r"C:\Users\jpowe\Desktop\Genesis",
    "AETHERIUS_OS": r"C:\Users\jpowe\Desktop\Aetherius-OS",
    "POIETEK": r"C:\Users\jpowe\Desktop\Poietek",
    "MAT": r"C:\Users\jpowe\Desktop\MAT",
    "ATHENA": r"C:\Users\jpowe\Desktop\ATHENA",
    "UNIVERSAL_BRIDGE": r"C:\Users\jpowe\Desktop\Universal-Bridge"
}

# Entry point patterns
ENTRY_POINTS = {
    "python_service": ["service.py", "app.py", "main.py", "server.py"],
    "python_cli": ["cli.py", "commands.py"],
    "node_dev": ["package.json"],  # Check for dev script
    "html_ui": ["index.html", "app.html"],
    "executable": ["*.exe", "*.bat", "*.ps1"],
    "startup_script": ["Start-*.ps1", "start-*.ps1", "run-*.ps1"]
}


def check_package_json(package_path):
    """Check if package.json has runnable scripts."""
    try:
        with open(package_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        scripts = pkg.get("scripts", {})
        return {
            "has_dev": "dev" in scripts,
            "has_build": "build" in scripts,
            "has_start": "start" in scripts,
            "scripts": list(scripts.keys())
        }
    except Exception:
        return None


def inventory_project(project_name, project_path):
    """Inventory runnable apps in a project."""
    results = {
        "project": project_name,
        "path": project_path,
        "exists": os.path.exists(project_path),
        "runnable_apps": [],
        "entry_points": {}
    }
    
    if not results["exists"]:
        return results
    
    # Search for entry points
    for root, dirs, files in os.walk(project_path):
        # Skip node_modules and .git
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", "__pycache__"]]
        
        for file in files:
            file_lower = file.lower()
            
            # Python services
            if file in ["service.py", "app.py", "main.py", "server.py"]:
                results["runnable_apps"].append({
                    "type": "python_service",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
            
            # Python CLI
            elif file in ["cli.py", "commands.py"]:
                results["runnable_apps"].append({
                    "type": "python_cli",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
            
            # Package.json
            elif file == "package.json":
                pkg_info = check_package_json(os.path.join(root, file))
                if pkg_info and pkg_info.get("has_dev"):
                    results["runnable_apps"].append({
                        "type": "node_dev",
                        "file": os.path.join(root, file),
                        "relative": os.path.relpath(os.path.join(root, file), project_path),
                        "scripts": pkg_info["scripts"]
                    })
            
            # HTML UIs
            elif file in ["index.html", "app.html"]:
                results["runnable_apps"].append({
                    "type": "html_ui",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
            
            # Startup scripts
            elif file.startswith("Start-") and file.endswith(".ps1"):
                results["runnable_apps"].append({
                    "type": "startup_script",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
            elif file.startswith("start-") and file.endswith(".ps1"):
                results["runnable_apps"].append({
                    "type": "startup_script",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
            elif file.startswith("run-") and file.endswith(".ps1"):
                results["runnable_apps"].append({
                    "type": "startup_script",
                    "file": os.path.join(root, file),
                    "relative": os.path.relpath(os.path.join(root, file), project_path)
                })
    
    return results


def main():
    """Main function."""
    print("Inventorying runnable first-party apps...")
    
    inventory = []
    for project_name, project_path in PROJECTS.items():
        print(f"\nChecking {project_name}...")
        result = inventory_project(project_name, project_path)
        inventory.append(result)
        
        if result["runnable_apps"]:
            print(f"  Found {len(result['runnable_apps'])} runnable apps:")
            for app in result["runnable_apps"]:
                print(f"    - {app['type']}: {app['relative']}")
        else:
            print("  No runnable apps found")
    
    # Save inventory
    output_file = r"E:\OpenCode-Data\conversation-analysis\RUNNABLE_APPS_INVENTORY.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=1)
    
    print(f"\nInventory saved to: {output_file}")
    
    # Summary
    total_apps = sum(len(result["runnable_apps"]) for result in inventory)
    print(f"\nTotal runnable apps found: {total_apps}")
    
    # Priority order for human testing
    print("\n== Priority Order for Human Testing ==")
    priority_order = [
        "IDE_WORKSPACE",
        "AGENT_BRIDGE",
        "GENESIS",
        "AETHERIUS_OS",
        "MAT",
        "UNIVERSAL_BRIDGE",
        "POIETEK",
        "ATHENA"
    ]
    
    for i, project in enumerate(priority_order, 1):
        result = next((r for r in inventory if r["project"] == project), None)
        if result and result["runnable_apps"]:
            print(f"{i}. {project}: {len(result['runnable_apps'])} apps")
            for app in result["runnable_apps"][:3]:  # Show first 3
                print(f"   - {app['type']}: {app['relative']}")
        elif result:
            print(f"{i}. {project}: NOT_RUNTIME_READY")
        else:
            print(f"{i}. {project}: NOT_FOUND")


if __name__ == "__main__":
    main()
