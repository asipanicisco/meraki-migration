#!/usr/bin/env python3
"""
Meraki Migration Tool - Server Version (Headless)
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
    api_key = os.environ.get('MERAKI_API_KEY')
    username = os.environ.get('MERAKI_USERNAME')
    password = os.environ.get('MERAKI_PASSWORD')
    
    if not all([api_key, username, password]):
        logger.error("Missing required environment variables")
        print("\nPlease set the following environment variables:")
        print("  export MERAKI_API_KEY='your-api-key'")
        print("  export MERAKI_USERNAME='your-email@company.com'")
        print("  export MERAKI_PASSWORD='your-password'")
        sys.exit(1)
    
    return api_key, username, password


def main():
    if len(sys.argv) != 4:
        print("Usage: python meraki_migration_server.py SOURCE_ORG_ID SOURCE_NETWORK_ID TARGET_ORG_ID")
        print("\nExample:")
        print("  python meraki_migration_server.py 123456 L_123456789 654321")
        print("\nNote: This server version runs Chrome in HEADLESS mode")
        print("      and uses environment variables for credentials")
        sys.exit(1)
    
    source_org_id = sys.argv[1]
    source_network_id = sys.argv[2]
    target_org_id = sys.argv[3]
    
    # Get credentials from environment
    api_key, username, password = get_credentials()
    
    logger.info(f"Starting automated migration (HEADLESS MODE)")
    logger.info(f"Source: Org {source_org_id}, Network {source_network_id}")
    logger.info(f"Target: Org {target_org_id}")
    
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
                tool = AutomatedMigrationTool(api_key, username, password)
                
                # Call the rest of the migration manually
                from meraki_auto_migration import MerakiAPIClient
                api = MerakiAPIClient(api_key)
                
                source_org_name = backup['org_name']
                target_org_name = api.get_org_name(target_org_id)
                
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
                
                # You can add the rest of the migration here or run it separately
                
        else:
            # Full migration from scratch
            tool = AutomatedMigrationTool(api_key, username, password)
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
