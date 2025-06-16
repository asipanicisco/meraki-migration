#!/usr/bin/env python3
"""
Meraki Migration Tool - Production Version
Uses environment variables for secure credential handling
"""

import os
import sys
from meraki_auto_migration import AutomatedMigrationTool
import logging
from datetime import datetime

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
        print("Usage: python meraki_migration.py SOURCE_ORG_ID SOURCE_NETWORK_ID TARGET_ORG_ID")
        print("\nExample:")
        print("  python meraki_migration.py 123456 L_123456789 654321")
        print("\nNote: This script uses environment variables for credentials:")
        print("  - MERAKI_API_KEY")
        print("  - MERAKI_USERNAME")
        print("  - MERAKI_PASSWORD")
        sys.exit(1)
    
    source_org_id = sys.argv[1]
    source_network_id = sys.argv[2]
    target_org_id = sys.argv[3]
    
    # Get credentials from environment
    api_key, username, password = get_credentials()
    
    logger.info(f"Starting automated migration")
    logger.info(f"Source: Org {source_org_id}, Network {source_network_id}")
    logger.info(f"Target: Org {target_org_id}")
    
    try:
        tool = AutomatedMigrationTool(api_key, username, password)
        target_network_id = tool.execute_migration(
            source_org_id,
            source_network_id,
            target_org_id
        )
        
        print(f"\n✓ Migration completed successfully!")
        print(f"  New network ID: {target_network_id}")
        print(f"  Check the log file for details: migration_*.log")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"\n✗ Migration failed: {e}")
        print("  Check the log file for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
