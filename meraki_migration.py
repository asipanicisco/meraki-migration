#!/usr/bin/env python3
"""
Meraki Migration Tool - Server Version (Headless) with Dual API Keys
Optimized for running on Linux servers without display
"""

import os
import sys
from meraki_auto_migration import AutomatedMigrationTool, MerakiUIAutomation
import logging
from datetime import datetime

# Monkey patch the MerakiUIAutomation to force headless mode
original_init = MerakiUIAutomation.__init__

def patched_init(self, username, password, headless=True):  # Force headless=True
    original_init(self, username, password, headless=True)

MerakiUIAutomation.__init__ = patched_init

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_credentials():
    """Get credentials from environment variables"""
    source_api_key = os.environ.get('MERAKI_SOURCE_API_KEY')
    target_api_key = os.environ.get('MERAKI_TARGET_API_KEY')
    username = os.environ.get('MERAKI_USERNAME')
    password = os.environ.get('MERAKI_PASSWORD')
    
    # Check if using single API key (backward compatibility)
    if not source_api_key or not target_api_key:
        single_api_key = os.environ.get('MERAKI_API_KEY')
        if single_api_key:
            logger.info("Using single API key for both source and target")
            source_api_key = single_api_key
            target_api_key = single_api_key
    
    if not all([source_api_key, target_api_key, username, password]):
        logger.error("Missing required environment variables")
        print("\nPlease set the following environment variables:")
        print("\nFor dual API key mode (recommended):")
        print("  export MERAKI_SOURCE_API_KEY='source-org-api-key'")
        print("  export MERAKI_TARGET_API_KEY='target-org-api-key'")
        print("\nFor single API key mode (backward compatibility):")
        print("  export MERAKI_API_KEY='your-api-key'")
        print("\nAnd always:")
        print("  export MERAKI_USERNAME='your-email@company.com'")
        print("  export MERAKI_PASSWORD='your-password'")
        sys.exit(1)
    
    return source_api_key, target_api_key, username, password


def main():
    if len(sys.argv) != 4:
        print("Usage: python meraki_migration_server.py SOURCE_ORG_ID SOURCE_NETWORK_ID TARGET_ORG_ID")
        print("\nExample:")
        print("  python meraki_migration_server.py 123456 L_123456789 654321")
        print("\nNote: This server version runs Chrome in HEADLESS mode")
        print("      and uses environment variables for credentials")
        print("\nDual API key mode (set both):")
        print("  - MERAKI_SOURCE_API_KEY")
        print("  - MERAKI_TARGET_API_KEY")
        print("\nSingle API key mode (backward compatibility):")
        print("  - MERAKI_API_KEY")
        sys.exit(1)
    
    source_org_id = sys.argv[1]
    source_network_id = sys.argv[2]
    target_org_id = sys.argv[3]
    
    # Get credentials from environment
    source_api_key, target_api_key, username, password = get_credentials()
    
    logger.info(f"Starting automated migration (HEADLESS MODE)")
    logger.info(f"Source: Org {source_org_id}, Network {source_network_id}")
    logger.info(f"Target: Org {target_org_id}")
    
    if source_api_key == target_api_key:
        logger.info("Using SINGLE API key for both organizations")
    else:
        logger.info("Using SEPARATE API keys for source and target organizations")
    
    try:
        # Check if we can continue from existing backup
        import glob
        import json
        
        backup_files = glob.glob(f'migration_backup_{source_network_id}_*.json')
        if backup_files:
            latest_backup = max(backup_files)
            print(f"\n📁 Found existing backup: {latest_backup}")
            
            use_backup = input("Use existing backup? (y/n): ").lower() == 'y'
            if use_backup:
                # Skip to UI automation part
                with open(latest_backup, 'r') as f:
                    backup = json.load(f)
                
                device_serials = [d['serial'] for d in backup['devices']]
                print(f"Found {len(device_serials)} devices in backup")
                
                # Continue from step 2
                logger.info("Continuing from existing backup...")
                tool = AutomatedMigrationTool(source_api_key, target_api_key, username, password)
                
                # Call the rest of the migration manually
                from meraki_auto_migration import MerakiAPIClient
                source_api = MerakiAPIClient(source_api_key)
                target_api = MerakiAPIClient(target_api_key)
                
                source_org_name = backup['org_name']
                target_org_name = target_api.get_org_name(target_org_id)
                
                # UI Automation part
                logger.info("=" * 50)
                logger.info("STEP 2: Moving devices via UI automation (HEADLESS)")
                logger.info("=" * 50)
                
                with MerakiUIAutomation(username, password, headless=True) as ui:
                    ui.login()
                    
                    # Unclaim from source
                    logger.info(f"Unclaiming devices from {source_org_name}")
                    if not ui.unclaim_devices(source_org_name, device_serials):
                        raise Exception("Failed to unclaim devices")
                    
                    # Wait for unclaim to process
                    logger.info("Waiting 120 seconds for unclaim to process...")
                    import time
                    time.sleep(120)
                    
                    # Claim in target
                    logger.info(f"Claiming devices in {target_org_name}")
                    if not ui.claim_devices(target_org_name, device_serials):
                        raise Exception("Failed to claim devices")
                
                # Continue with network creation and restoration...
                logger.info("Devices moved successfully! Continue with network creation.")
                
                # Wait for claim to process
                logger.info("Waiting 30 seconds for claim to process...")
                time.sleep(30)
                
                # Step 3: Create network and add devices
                logger.info("=" * 50)
                logger.info("STEP 3: Creating network and adding devices")
                logger.info("=" * 50)
                
                # Create network
                network_name = f"{backup['network_info']['name']}_migrated"
                network_config = {
                    "name": network_name,
                    "productTypes": backup['network_info'].get('productTypes', ['switch']),
                    "timeZone": backup['network_info'].get('timeZone', 'America/Los_Angeles')
                }
                
                target_network_id = target_api.create_network(target_org_id, network_config)
                logger.info(f"Created network: {target_network_id}")
                
                # Add devices to network
                if target_api.add_devices_to_network(target_network_id, device_serials):
                    logger.info("Devices added to network")
                else:
                    logger.warning("Failed to add some devices to network")
                
                # Wait for devices to be ready
                time.sleep(10)
                
                # Step 4: Restore settings
                logger.info("=" * 50)
                logger.info("STEP 4: Restoring all settings")
                logger.info("=" * 50)
                
                # Create device mapping (same serials in this case)
                device_mapping = {serial: serial for serial in device_serials}
                
                from meraki_auto_migration import ComprehensiveRestore
                restore_tool = ComprehensiveRestore(target_api)
                restore_tool.restore_all_settings(backup, target_network_id, device_mapping)
                
                print(f"\n✓ Migration completed successfully!")
                print(f"  New network ID: {target_network_id}")
                
        else:
            # Full migration from scratch
            tool = AutomatedMigrationTool(source_api_key, target_api_key, username, password)
            target_network_id = tool.execute_migration(
                source_org_id,
                source_network_id,
                target_org_id
            )
            
            print(f"\n✓ Migration completed successfully!")
            print(f"  New network ID: {target_network_id}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"\n✗ Migration failed: {e}")
        print("\nCheck the log file for details")
        print("\nIf Chrome failed, try:")
        print("1. Run: pkill -f chrome")
        print("2. Check Chrome installation: google-chrome --version")
        print("3. Check if running on a server without display")
        sys.exit(1)


if __name__ == "__main__":
    main()
