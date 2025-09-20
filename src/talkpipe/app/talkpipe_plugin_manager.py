# talkpipe/app/plugin_manager.py
import argparse
from talkpipe.util.plugin_loader import (
    get_plugin_loader, 
    list_loaded_plugins, 
    list_failed_plugins
)

def main():
    parser = argparse.ArgumentParser(description='Manage TalkPipe plugins')
    parser.add_argument('--list', action='store_true', 
                       help='List all plugins')
    parser.add_argument('--reload', type=str, 
                       help='Reload a specific plugin')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed information')
    
    args = parser.parse_args()
    
    if args.list:
        loaded = list_loaded_plugins()
        failed = list_failed_plugins()
        
        print("=== TalkPipe Plugins ===")
        print(f"Loaded plugins ({len(loaded)}):")
        for plugin in loaded:
            print(f"  ✓ {plugin}")
        
        if failed:
            print(f"\nFailed plugins ({len(failed)}):")
            for plugin in failed:
                print(f"  ✗ {plugin}")
    
    if args.reload:
        loader = get_plugin_loader()
        success = loader.reload_plugin(args.reload)
        if success:
            print(f"Successfully reloaded plugin: {args.reload}")
        else:
            print(f"Failed to reload plugin: {args.reload}")

if __name__ == "__main__":
    main()