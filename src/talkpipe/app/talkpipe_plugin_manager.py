# talkpipe/app/plugin_manager.py
import argparse
from talkpipe.util.plugin_loader import (
    get_plugin_loader,
    list_loaded_plugins,
    list_failed_plugins
)
from talkpipe.chatterlang.registry import segment_registry, input_registry, DEPRECATED_ALIASES

def main():
    parser = argparse.ArgumentParser(description='Manage TalkPipe plugins')
    parser.add_argument('--list', action='store_true',
                       help='List all plugins')
    parser.add_argument('--reload', type=str,
                       help='Reload a specific plugin')
    parser.add_argument('--verbose', action='store_true',
                       help='Show detailed information')

    args = parser.parse_args()

    # A bare invocation with no flags should show something useful rather than
    # silently doing nothing, so default to --list.
    if not (args.list or args.reload):
        args.list = True

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

        # Components registered via `talkpipe.segments` / `talkpipe.sources` entry
        # points (not the `talkpipe.plugins` group above) are a separate mechanism;
        # list them too since they're otherwise invisible to this command.
        segments = {
            name: target for name, target in segment_registry.list_entry_points().items()
            if name not in DEPRECATED_ALIASES
        }
        sources = {
            name: target for name, target in input_registry.list_entry_points().items()
            if name not in DEPRECATED_ALIASES
        }

        print(f"\nSegments registered via 'talkpipe.segments' entry points ({len(segments)}):")
        for name, target in sorted(segments.items()):
            print(f"  {name} -> {target}")

        print(f"\nSources registered via 'talkpipe.sources' entry points ({len(sources)}):")
        for name, target in sorted(sources.items()):
            print(f"  {name} -> {target}")
    
    if args.reload:
        loader = get_plugin_loader()
        success = loader.reload_plugin(args.reload)
        if success:
            print(f"Successfully reloaded plugin: {args.reload}")
        else:
            print(f"Failed to reload plugin: {args.reload}")

if __name__ == "__main__":
    main()