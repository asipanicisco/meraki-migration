#!/usr/bin/env python3
"""
Meraki Network Settings Migration Tool - Enhanced for Switch Networks
Backs up all network and device settings from a source organization/network
and allows restoration to a new organization/network.
"""

import json
import logging
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'meraki_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MerakiMigrator:
    """Handles migration of Meraki network settings between organizations"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            "X-Cisco-Meraki-API-Key": api_key,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _api_call(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                  params: Optional[Dict] = None) -> Any:
        """Make API call with retry logic"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(3):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                )
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                return None
                
            except requests.exceptions.RequestException as e:
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    
    def get_organizations(self) -> List[Dict]:
        """Get all organizations accessible with the API key"""
        return self._api_call("GET", "/organizations")
    
    def get_networks(self, org_id: str) -> List[Dict]:
        """Get all networks in an organization"""
        return self._api_call("GET", f"/organizations/{org_id}/networks")
    
    def get_devices(self, network_id: str) -> List[Dict]:
        """Get all devices in a network"""
        return self._api_call("GET", f"/networks/{network_id}/devices")
    
    def backup_organization_settings(self, org_id: str) -> Dict:
        """Backup organization-level settings"""
        logger.info(f"Backing up organization settings for {org_id}")
        
        org_settings = {}
        
        # Organization-wide settings that affect switches
        org_endpoints = {
            "configTemplates": f"/organizations/{org_id}/configTemplates",
            "adaptivePolicy": {
                "settings": f"/organizations/{org_id}/adaptivePolicy/settings",
                "acls": f"/organizations/{org_id}/adaptivePolicy/acls",
                "groups": f"/organizations/{org_id}/adaptivePolicy/groups",
                "policies": f"/organizations/{org_id}/adaptivePolicy/policies"
            },
            "samlRoles": f"/organizations/{org_id}/samlRoles",
            "policyObjects": {
                "groups": f"/organizations/{org_id}/policyObjects/groups",
                "objects": f"/organizations/{org_id}/policyObjects"
            },
            "loginSecurity": f"/organizations/{org_id}/loginSecurity",
            "snmp": f"/organizations/{org_id}/snmp"
        }
        
        for setting_name, endpoints in org_endpoints.items():
            if isinstance(endpoints, dict):
                org_settings[setting_name] = {}
                for sub_name, endpoint in endpoints.items():
                    try:
                        org_settings[setting_name][sub_name] = self._api_call("GET", endpoint)
                        logger.info(f"Backed up {setting_name}/{sub_name}")
                    except Exception as e:
                        logger.warning(f"Could not backup {setting_name}/{sub_name}: {e}")
            else:
                try:
                    org_settings[setting_name] = self._api_call("GET", endpoints)
                    logger.info(f"Backed up {setting_name}")
                except Exception as e:
                    logger.warning(f"Could not backup {setting_name}: {e}")
        
        return org_settings
    
    def backup_switch_network_settings(self, network_id: str) -> Dict:
        """Backup switch-specific network settings"""
        logger.info(f"Backing up switch network settings for {network_id}")
        
        switch_settings = {}
        
        # Switch-specific network settings
        switch_endpoints = {
            "settings": f"/networks/{network_id}/switch/settings",
            "accessPolicies": f"/networks/{network_id}/switch/accessPolicies",
            "alternateManagementInterface": f"/networks/{network_id}/switch/alternateManagementInterface",
            "dhcpServerPolicy": f"/networks/{network_id}/switch/dhcpServerPolicy",
            "dscp": f"/networks/{network_id}/switch/dscp",
            "mtu": f"/networks/{network_id}/switch/mtu",
            "portSchedules": f"/networks/{network_id}/switch/portSchedules",
            "qosRules": f"/networks/{network_id}/switch/qosRules",
            "stormControl": f"/networks/{network_id}/switch/stormControl",
            "stp": f"/networks/{network_id}/switch/stp",
            "routingMulticast": f"/networks/{network_id}/switch/routing/multicast",
            "routingOspf": f"/networks/{network_id}/switch/routing/ospf",
            "warmSpare": f"/networks/{network_id}/switch/warmSpare",
            "stacks": f"/networks/{network_id}/switch/stacks",
            "linkAggregations": f"/networks/{network_id}/switch/linkAggregations",
            "portMirror": f"/networks/{network_id}/switch/portMirror"
        }
        
        for setting_name, endpoint in switch_endpoints.items():
            try:
                switch_settings[setting_name] = self._api_call("GET", endpoint)
                logger.info(f"Backed up switch {setting_name}")
            except Exception as e:
                logger.warning(f"Could not backup switch {setting_name}: {e}")
        
        return switch_settings
    
    def backup_switch_ports(self, device_serial: str) -> List[Dict]:
        """Backup all port configurations for a switch"""
        try:
            ports = self._api_call("GET", f"/devices/{device_serial}/switch/ports")
            
            # Get additional port details
            for port in ports:
                port_number = port['portId']
                
                # Port statuses
                try:
                    port['status'] = self._api_call(
                        "GET", f"/devices/{device_serial}/switch/ports/{port_number}/statuses"
                    )
                except Exception:
                    pass
                
            return ports
        except Exception as e:
            logger.warning(f"Could not backup ports for {device_serial}: {e}")
            return []
    
    def backup_network_settings(self, org_id: str, network_id: str, include_org_settings: bool = True) -> Dict:
        """Backup all settings for a network with enhanced switch support"""
        logger.info(f"Starting backup for network {network_id}")
        
        backup = {
            "timestamp": datetime.now().isoformat(),
            "org_id": org_id,
            "network_id": network_id,
            "network_info": {},
            "devices": [],
            "settings": {},
            "switch_settings": {},
            "org_settings": {}
        }
        
        # Get organization settings if requested
        if include_org_settings:
            backup["org_settings"] = self.backup_organization_settings(org_id)
        
        # Get network info
        try:
            backup["network_info"] = self._api_call("GET", f"/networks/{network_id}")
            logger.info("Backed up network info")
        except Exception as e:
            logger.error(f"Failed to get network info: {e}")
        
        # Get devices
        try:
            devices = self.get_devices(network_id)
            backup["devices"] = devices
            logger.info(f"Found {len(devices)} devices")
            
            # Get device-specific settings
            for device in devices:
                device_serial = device['serial']
                device['configurations'] = {}
                
                # Management interface settings
                try:
                    device['configurations']['management'] = self._api_call(
                        "GET", f"/devices/{device_serial}/managementInterface"
                    )
                except Exception as e:
                    logger.warning(f"Could not get management interface for {device_serial}: {e}")
                
                # Switch-specific configurations
                if device.get('model', '').startswith('MS'):
                    # Switch ports with full configuration
                    device['configurations']['switchPorts'] = self.backup_switch_ports(device_serial)
                    
                    # Switch routing interfaces
                    try:
                        device['configurations']['routingInterfaces'] = self._api_call(
                            "GET", f"/devices/{device_serial}/switch/routing/interfaces"
                        )
                    except Exception:
                        pass
                    
                    # Switch routing static routes
                    try:
                        device['configurations']['routingStaticRoutes'] = self._api_call(
                            "GET", f"/devices/{device_serial}/switch/routing/staticRoutes"
                        )
                    except Exception:
                        pass
                    
                    # Switch warm spare
                    try:
                        device['configurations']['warmSpare'] = self._api_call(
                            "GET", f"/devices/{device_serial}/switch/warmSpare"
                        )
                    except Exception:
                        pass
                
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
        
        # Get switch-specific network settings
        backup["switch_settings"] = self.backup_switch_network_settings(network_id)
        
        # General network-wide settings
        settings_endpoints = {
            "vlans": f"/networks/{network_id}/appliance/vlans",
            "groupPolicies": f"/networks/{network_id}/groupPolicies",
            "alerts": f"/networks/{network_id}/alerts/settings",
            "syslog": f"/networks/{network_id}/syslogServers",
            "snmp": f"/networks/{network_id}/snmp",
            "netflow": f"/networks/{network_id}/netflow",
            "floorplans": f"/networks/{network_id}/floorPlans",
            "httpServers": f"/networks/{network_id}/httpServers",
            "webhooks": f"/networks/{network_id}/webhooks/httpServers",
            "trafficAnalysis": f"/networks/{network_id}/trafficAnalysis"
        }
        
        for setting_name, endpoint in settings_endpoints.items():
            try:
                backup["settings"][setting_name] = self._api_call("GET", endpoint)
                logger.info(f"Backed up {setting_name}")
            except Exception as e:
                logger.warning(f"Could not backup {setting_name}: {e}")
        
        return backup
    
    def create_network(self, org_id: str, network_config: Dict) -> str:
        """Create a new network in the target organization"""
        data = {
            "name": network_config.get("name", "Migrated Network"),
            "productTypes": network_config.get("productTypes", ["switch"]),
            "timeZone": network_config.get("timeZone", "America/Los_Angeles"),
            "tags": network_config.get("tags", []),
            "notes": network_config.get("notes", "")
        }
        
        result = self._api_call("POST", f"/organizations/{org_id}/networks", data=data)
        return result["id"]
    
    def restore_switch_ports(self, device_serial: str, ports_config: List[Dict]):
        """Restore port configurations to a switch"""
        for port in ports_config:
            port_id = port['portId']
            
            # Remove read-only fields
            port_data = {k: v for k, v in port.items() 
                        if k not in ['portId', 'status', 'warnings', 'errors', 'speed', 'duplex']}
            
            try:
                self._api_call("PUT", f"/devices/{device_serial}/switch/ports/{port_id}", 
                             data=port_data)
                logger.info(f"Restored port {port_id} on {device_serial}")
            except Exception as e:
                logger.warning(f"Could not restore port {port_id} on {device_serial}: {e}")
    
    def restore_switch_network_settings(self, backup: Dict, target_network_id: str):
        """Restore switch-specific network settings"""
        switch_settings = backup.get("switch_settings", {})
        
        for setting_name, setting_data in switch_settings.items():
            if not setting_data:
                continue
            
            endpoint_map = {
                "settings": f"/networks/{target_network_id}/switch/settings",
                "accessPolicies": f"/networks/{target_network_id}/switch/accessPolicies",
                "alternateManagementInterface": f"/networks/{target_network_id}/switch/alternateManagementInterface",
                "dhcpServerPolicy": f"/networks/{target_network_id}/switch/dhcpServerPolicy",
                "dscp": f"/networks/{target_network_id}/switch/dscp",
                "mtu": f"/networks/{target_network_id}/switch/mtu",
                "qosRules": f"/networks/{target_network_id}/switch/qosRules",
                "stormControl": f"/networks/{target_network_id}/switch/stormControl",
                "stp": f"/networks/{target_network_id}/switch/stp"
            }
            
            if setting_name not in endpoint_map:
                logger.warning(f"Skipping switch setting {setting_name} - restoration not implemented")
                continue
            
            try:
                if setting_name == "accessPolicies" and isinstance(setting_data, list):
                    for policy in setting_data:
                        policy_data = {k: v for k, v in policy.items() 
                                     if k not in ['accessPolicyNumber']}
                        self._api_call("POST", endpoint_map[setting_name], data=policy_data)
                
                elif setting_name == "qosRules" and isinstance(setting_data, list):
                    for rule in setting_data:
                        rule_data = {k: v for k, v in rule.items() if k != 'id'}
                        self._api_call("POST", endpoint_map[setting_name], data=rule_data)
                
                elif setting_name in ["settings", "dhcpServerPolicy", "dscp", "mtu", 
                                    "stormControl", "stp", "alternateManagementInterface"]:
                    self._api_call("PUT", endpoint_map[setting_name], data=setting_data)
                
                logger.info(f"Restored switch setting {setting_name}")
                
            except Exception as e:
                logger.error(f"Failed to restore switch setting {setting_name}: {e}")
    
    def restore_network_settings(self, backup: Dict, target_org_id: str, 
                               target_network_id: Optional[str] = None,
                               device_mapping: Optional[Dict[str, str]] = None) -> str:
        """Restore settings to a target organization/network"""
        logger.info(f"Starting restoration to org {target_org_id}")
        
        # Create new network if not specified
        if not target_network_id:
            network_name = backup["network_info"].get("name", "Migrated Network")
            network_name = f"{network_name}_migrated_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            network_config = backup["network_info"].copy()
            network_config["name"] = network_name
            
            target_network_id = self.create_network(target_org_id, network_config)
            logger.info(f"Created new network: {target_network_id}")
        
        # Restore switch-specific network settings
        self.restore_switch_network_settings(backup, target_network_id)
        
        # Restore general network-wide settings
        for setting_name, setting_data in backup["settings"].items():
            if not setting_data:
                continue
                
            endpoint_map = {
                "groupPolicies": f"/networks/{target_network_id}/groupPolicies",
                "alerts": f"/networks/{target_network_id}/alerts/settings",
                "syslog": f"/networks/{target_network_id}/syslogServers",
                "snmp": f"/networks/{target_network_id}/snmp",
                "webhooks": f"/networks/{target_network_id}/webhooks/httpServers"
            }
            
            if setting_name not in endpoint_map:
                logger.warning(f"Skipping {setting_name} - restoration not implemented")
                continue
            
            try:
                if setting_name in ["alerts", "snmp"]:
                    self._api_call("PUT", endpoint_map[setting_name], data=setting_data)
                
                elif isinstance(setting_data, list):
                    for item in setting_data:
                        item_data = {k: v for k, v in item.items() 
                                   if k not in ["id", "networkId"]}
                        self._api_call("POST", endpoint_map[setting_name], data=item_data)
                
                logger.info(f"Restored {setting_name}")
                
            except Exception as e:
                logger.error(f"Failed to restore {setting_name}: {e}")
        
        # Restore device configurations if device mapping provided
        if device_mapping:
            logger.info("Restoring device configurations based on mapping")
            for device in backup["devices"]:
                old_serial = device['serial']
                new_serial = device_mapping.get(old_serial)
                
                if not new_serial:
                    logger.warning(f"No mapping found for device {old_serial}")
                    continue
                
                # Restore switch ports
                if 'switchPorts' in device.get('configurations', {}):
                    self.restore_switch_ports(new_serial, 
                                            device['configurations']['switchPorts'])
        
        logger.info("Network settings restored.")
        return target_network_id
    
    def save_backup(self, backup: Dict, filename: str):
        """Save backup to JSON file"""
        with open(filename, 'w') as f:
            json.dump(backup, f, indent=2)
        logger.info(f"Backup saved to {filename}")
    
    def load_backup(self, filename: str) -> Dict:
        """Load backup from JSON file"""
        with open(filename, 'r') as f:
            backup = json.load(f)
        logger.info(f"Backup loaded from {filename}")
        return backup
    
    def generate_device_mapping_template(self, backup: Dict, filename: str):
        """Generate a device mapping template file"""
        mapping = {}
        for device in backup.get("devices", []):
            mapping[device['serial']] = {
                "old_serial": device['serial'],
                "old_name": device.get('name', ''),
                "old_model": device.get('model', ''),
                "new_serial": "ENTER_NEW_SERIAL_HERE"
            }
        
        with open(filename, 'w') as f:
            json.dump(mapping, f, indent=2)
        logger.info(f"Device mapping template saved to {filename}")
    
    def generate_migration_checklist(self, backup: Dict, filename: str):
        """Generate a detailed migration checklist"""
        checklist = {
            "migration_info": {
                "source_org": backup.get("org_id"),
                "source_network": backup.get("network_id"),
                "backup_timestamp": backup.get("timestamp"),
                "total_devices": len(backup.get("devices", []))
            },
            "devices_to_migrate": [],
            "migration_steps": [
                "1. Log into source organization Dashboard",
                "2. Go to Organization > Inventory",
                "3. Select all devices listed below",
                "4. Click 'Remove from organization'",
                "5. Log into target organization Dashboard",
                "6. Go to Organization > Inventory > Claim",
                "7. Enter serial numbers or order numbers",
                "8. Add devices to the new network",
                "9. Update device mapping file if serials changed",
                "10. Run restore command with device mapping"
            ]
        }
        
        # Device details for migration
        for device in backup.get("devices", []):
            device_info = {
                "serial": device['serial'],
                "name": device.get('name', 'Unnamed'),
                "model": device.get('model', ''),
                "mac": device.get('mac', ''),
                "tags": device.get('tags', []),
                "notes": device.get('notes', ''),
                "port_count": len(device.get('configurations', {}).get('switchPorts', [])),
                "claimed": False,
                "claim_info": self._extract_claim_info(device)
            }
            checklist["devices_to_migrate"].append(device_info)
        
        # Save checklist
        with open(filename, 'w') as f:
            json.dump(checklist, f, indent=2)
        
        # Also create a simple text version
        text_filename = filename.replace('.json', '.txt')
        with open(text_filename, 'w') as f:
            f.write("MERAKI SWITCH MIGRATION CHECKLIST\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Source Org: {checklist['migration_info']['source_org']}\n")
            f.write(f"Source Network: {checklist['migration_info']['source_network']}\n")
            f.write(f"Total Devices: {checklist['migration_info']['total_devices']}\n")
            f.write(f"Backup Created: {checklist['migration_info']['backup_timestamp']}\n\n")
            
            f.write("DEVICES TO MIGRATE:\n")
            f.write("-" * 50 + "\n")
            for device in checklist['devices_to_migrate']:
                f.write(f"\nSerial: {device['serial']}\n")
                f.write(f"Name: {device['name']}\n")
                f.write(f"Model: {device['model']}\n")
                f.write(f"MAC: {device['mac']}\n")
                if device['claim_info']:
                    f.write(f"Claim Info: {device['claim_info']}\n")
                f.write(f"Port Count: {device['port_count']}\n")
            
            f.write("\n" + "=" * 50 + "\n")
            f.write("MIGRATION STEPS:\n")
            for step in checklist['migration_steps']:
                f.write(f"{step}\n")
        
        logger.info(f"Migration checklist saved to {filename} and {text_filename}")
        return checklist
    
    def _extract_claim_info(self, device: Dict) -> Optional[str]:
        """Extract claim information from device notes or tags"""
        # Check notes for order numbers or claim codes
        notes = device.get('notes', '')
        tags = ' '.join(device.get('tags', []))
        
        # Look for common patterns
        import re
        order_pattern = r'order[:\s#-]+(\w+)'
        claim_pattern = r'claim[:\s#-]+(\w+)'
        
        order_match = re.search(order_pattern, notes + ' ' + tags, re.IGNORECASE)
        claim_match = re.search(claim_pattern, notes + ' ' + tags, re.IGNORECASE)
        
        if order_match:
            return f"Order: {order_match.group(1)}"
        elif claim_match:
            return f"Claim: {claim_match.group(1)}"
        return None
    
    def verify_devices_in_target(self, target_org_id: str, device_serials: List[str]) -> Dict[str, bool]:
        """Check which devices are present in target organization"""
        try:
            # Get inventory from target org
            inventory = self._api_call("GET", f"/organizations/{target_org_id}/inventory/devices")
            
            # Create set of serials in target org
            target_serials = {device['serial'] for device in inventory}
            
            # Check each device
            results = {}
            for serial in device_serials:
                results[serial] = serial in target_serials
            
            return results
        except Exception as e:
            logger.error(f"Failed to verify devices in target org: {e}")
            return {serial: False for serial in device_serials}
    
    def wait_for_devices(self, target_org_id: str, expected_serials: List[str], 
                        target_network_id: Optional[str] = None, timeout: int = 300):
        """Wait for devices to appear in target organization"""
        logger.info(f"Waiting for {len(expected_serials)} devices to appear in target organization...")
        start_time = time.time()
        
        # Track which devices have been found
        found_devices = set()
        network_devices = set()
        
        while time.time() - start_time < timeout:
            # Check organization inventory
            device_status = self.verify_devices_in_target(target_org_id, expected_serials)
            newly_found = set()
            
            for serial, found in device_status.items():
                if found and serial not in found_devices:
                    newly_found.add(serial)
                    found_devices.add(serial)
                    logger.info(f"✓ Device {serial} found in organization inventory")
            
            # If all devices found in org, check if they're in the network
            if len(found_devices) == len(expected_serials):
                if target_network_id:
                    try:
                        network_devs = self.get_devices(target_network_id)
                        network_serials = {d['serial'] for d in network_devs}
                        
                        for serial in expected_serials:
                            if serial in network_serials and serial not in network_devices:
                                network_devices.add(serial)
                                logger.info(f"✓ Device {serial} added to network")
                        
                        if len(network_devices) == len(expected_serials):
                            logger.info("All devices successfully added to network!")
                            return True
                    except Exception:
                        pass
                else:
                    logger.info("All devices found in organization inventory!")
                    return True
            
            # Show progress
            remaining = set(expected_serials) - found_devices
            if remaining:
                logger.info(f"Still waiting for {len(remaining)} devices: {', '.join(remaining)}")
            
            time.sleep(10)  # Check every 10 seconds
        
        # Timeout reached
        missing = set(expected_serials) - found_devices
        if missing:
            logger.warning(f"Timeout: Still missing {len(missing)} devices: {', '.join(missing)}")
        return False
    
    def update_device_notes(self, network_id: str, claim_info: Dict[str, str]) -> Dict[str, bool]:
        """Update device notes with claim information"""
        logger.info("Updating device notes with claim information...")
        results = {}
        
        try:
            devices = self.get_devices(network_id)
            
            for device in devices:
                serial = device['serial']
                if serial not in claim_info:
                    continue
                
                current_notes = device.get('notes', '')
                new_info = claim_info[serial]
                
                # Check if claim info already exists
                if new_info.lower() in current_notes.lower():
                    logger.info(f"Device {serial} already has claim info in notes")
                    results[serial] = True
                    continue
                
                # Append claim info to notes
                if current_notes:
                    updated_notes = f"{current_notes}\n{new_info}"
                else:
                    updated_notes = new_info
                
                # Update device
                try:
                    self._api_call("PUT", f"/devices/{serial}", 
                                 data={"notes": updated_notes})
                    logger.info(f"Updated notes for device {serial}")
                    results[serial] = True
                except Exception as e:
                    logger.error(f"Failed to update notes for {serial}: {e}")
                    results[serial] = False
                    
        except Exception as e:
            logger.error(f"Failed to update device notes: {e}")
            
        return results
    
    def tag_devices_for_migration(self, network_id: str, tag: str = "migration-pending") -> Dict[str, bool]:
        """Add a migration tag to all devices in the network"""
        logger.info(f"Tagging devices with '{tag}'...")
        results = {}
        
        try:
            devices = self.get_devices(network_id)
            
            for device in devices:
                serial = device['serial']
                current_tags = device.get('tags', [])
                
                if tag in current_tags:
                    logger.info(f"Device {serial} already tagged")
                    results[serial] = True
                    continue
                
                # Add tag
                updated_tags = current_tags + [tag]
                
                try:
                    self._api_call("PUT", f"/devices/{serial}", 
                                 data={"tags": updated_tags})
                    logger.info(f"Tagged device {serial}")
                    results[serial] = True
                except Exception as e:
                    logger.error(f"Failed to tag {serial}: {e}")
                    results[serial] = False
                    
        except Exception as e:
            logger.error(f"Failed to tag devices: {e}")
            
        return results
    
    def generate_inventory_report(self, org_id: str, network_id: str, filename: str):
        """Generate a detailed inventory report for migration"""
        logger.info("Generating inventory report...")
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "organization": {},
            "network": {},
            "devices": [],
            "summary": {}
        }
        
        # Get organization info
        try:
            orgs = self.get_organizations()
            report["organization"] = next((o for o in orgs if o['id'] == org_id), {})
        except Exception:
            pass
        
        # Get network info
        try:
            report["network"] = self._api_call("GET", f"/networks/{network_id}")
        except Exception:
            pass
        
        # Get detailed device inventory
        try:
            devices = self.get_devices(network_id)
            
            for device in devices:
                # Get additional device details
                device_detail = {
                    "serial": device['serial'],
                    "name": device.get('name', ''),
                    "model": device.get('model', ''),
                    "mac": device.get('mac', ''),
                    "firmware": device.get('firmware', ''),
                    "tags": device.get('tags', []),
                    "notes": device.get('notes', ''),
                    "address": device.get('address', ''),
                    "lanIp": device.get('lanIp', ''),
                    "wan1Ip": device.get('wan1Ip', ''),
                    "wan2Ip": device.get('wan2Ip', '')
                }
                
                # Get uplink info if available
                try:
                    uplinks = self._api_call("GET", f"/devices/{device['serial']}/switch/ports/statuses")
                    uplink_ports = [p for p in uplinks if p.get('status') == 'Connected' and 
                                  p.get('speed', '').endswith('Gbps')]
                    device_detail['uplinks'] = uplink_ports
                except Exception:
                    device_detail['uplinks'] = []
                
                report["devices"].append(device_detail)
        except Exception as e:
            logger.error(f"Failed to get device inventory: {e}")
        
        # Generate summary
        report["summary"] = {
            "total_devices": len(report["devices"]),
            "device_models": {},
            "total_ports": 0
        }
        
        for device in report["devices"]:
            model = device.get('model', 'Unknown')
            report["summary"]["device_models"][model] = \
                report["summary"]["device_models"].get(model, 0) + 1
        
        # Save report
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Create CSV version for easy reference
        csv_filename = filename.replace('.json', '.csv')
        with open(csv_filename, 'w') as f:
            f.write("Serial,Name,Model,MAC,IP,Firmware,Tags,Notes\n")
            for device in report["devices"]:
                f.write(f"{device['serial']},{device['name']},{device['model']},")
                f.write(f"{device['mac']},{device.get('lanIp', '')},{device['firmware']},")
                f.write(f"\"{';'.join(device['tags'])}\",\"{device['notes']}\"\n")
        
        logger.info(f"Inventory report saved to {filename} and {csv_filename}")
        return report


def main():
    parser = argparse.ArgumentParser(description="Meraki Network Settings Migration Tool")
    parser.add_argument("--api-key", required=True, help="Meraki API key")
    parser.add_argument("--mode", choices=["backup", "restore", "migrate", "verify", "wait", "inventory", "prepare"], 
                       required=True, help="Operation mode")
    parser.add_argument("--source-org", help="Source organization ID")
    parser.add_argument("--source-network", help="Source network ID")
    parser.add_argument("--target-org", help="Target organization ID")
    parser.add_argument("--target-network", help="Target network ID (optional)")
    parser.add_argument("--backup-file", help="Backup file path")
    parser.add_argument("--device-mapping", help="Device mapping JSON file")
    parser.add_argument("--claim-info", help="JSON file with serial-to-claim-info mapping")
    parser.add_argument("--add-tag", help="Tag to add to devices (for prepare mode)")
    parser.add_argument("--include-org-settings", action="store_true", 
                       help="Include organization-level settings in backup")
    parser.add_argument("--generate-mapping", action="store_true",
                       help="Generate device mapping template from backup")
    parser.add_argument("--generate-checklist", action="store_true",
                       help="Generate migration checklist from backup")
    parser.add_argument("--list-orgs", action="store_true", help="List available organizations")
    parser.add_argument("--list-networks", help="List networks for given org ID")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout for wait mode (seconds)")
    
    args = parser.parse_args()
    
    migrator = MerakiMigrator(args.api_key)
    
    # List organizations
    if args.list_orgs:
        orgs = migrator.get_organizations()
        print("\nAvailable Organizations:")
        for org in orgs:
            print(f"  - {org['name']} (ID: {org['id']})")
        return
    
    # List networks
    if args.list_networks:
        networks = migrator.get_networks(args.list_networks)
        print(f"\nNetworks in organization {args.list_networks}:")
        for network in networks:
            print(f"  - {network['name']} (ID: {network['id']})")
        return
    
    # Generate device mapping template
    if args.generate_mapping:
        if not args.backup_file:
            parser.error("--generate-mapping requires --backup-file")
        
        backup = migrator.load_backup(args.backup_file)
        mapping_file = args.backup_file.replace('.json', '_device_mapping.json')
        migrator.generate_device_mapping_template(backup, mapping_file)
        print(f"\nDevice mapping template generated: {mapping_file}")
        print("Edit this file to map old device serials to new ones before restoring")
        return
    
    # Generate migration checklist
    if args.generate_checklist:
        if not args.backup_file:
            parser.error("--generate-checklist requires --backup-file")
        
        backup = migrator.load_backup(args.backup_file)
        checklist_file = args.backup_file.replace('.json', '_checklist.json')
        checklist = migrator.generate_migration_checklist(backup, checklist_file)
        print(f"\nMigration checklist generated: {checklist_file}")
        print(f"Text version: {checklist_file.replace('.json', '.txt')}")
        print(f"Total devices to migrate: {len(checklist['devices_to_migrate'])}")
        return
    
    # Backup mode
    if args.mode == "backup":
        if not args.source_org or not args.source_network:
            parser.error("Backup mode requires --source-org and --source-network")
        
        backup = migrator.backup_network_settings(
            args.source_org, 
            args.source_network,
            include_org_settings=args.include_org_settings
        )
        
        filename = args.backup_file or f"meraki_backup_{args.source_network}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        migrator.save_backup(backup, filename)
        
        # Generate device mapping template
        mapping_file = filename.replace('.json', '_device_mapping.json')
        migrator.generate_device_mapping_template(backup, mapping_file)
        
        # Generate migration checklist
        checklist_file = filename.replace('.json', '_checklist.json')
        checklist = migrator.generate_migration_checklist(backup, checklist_file)
        
        print(f"\n✓ Backup complete!")
        print(f"  - Backup file: {filename}")
        print(f"  - Device mapping: {mapping_file}")
        print(f"  - Migration checklist: {checklist_file}")
        print(f"  - Text checklist: {checklist_file.replace('.json', '.txt')}")
        print(f"\nTotal devices to migrate: {len(checklist['devices_to_migrate'])}")
        print("\nNext steps:")
        print("1. Review the migration checklist")
        print("2. Remove devices from source organization")
        print("3. Claim devices in target organization")
        print("4. Update device mapping if serials changed")
        print("5. Run restore with --device-mapping")
    
    # Prepare mode
    elif args.mode == "prepare":
        if not args.source_network:
            parser.error("Prepare mode requires --source-network")
        
        print(f"\nPreparing devices for migration in network {args.source_network}")
        
        # Tag devices if requested
        if args.add_tag:
            results = migrator.tag_devices_for_migration(args.source_network, args.add_tag)
            success_count = sum(1 for v in results.values() if v)
            print(f"\n✓ Tagged {success_count}/{len(results)} devices with '{args.add_tag}'")
        
        # Update notes with claim info if provided
        if args.claim_info:
            try:
                with open(args.claim_info, 'r') as f:
                    claim_mapping = json.load(f)
                
                # Convert to format expected by update_device_notes
                claim_info = {}
                for serial, info in claim_mapping.items():
                    if isinstance(info, dict):
                        # Handle different formats
                        if 'order' in info:
                            claim_info[serial] = f"Order: {info['order']}"
                        elif 'claim' in info:
                            claim_info[serial] = f"Claim: {info['claim']}"
                        else:
                            claim_info[serial] = str(info)
                    else:
                        claim_info[serial] = str(info)
                
                results = migrator.update_device_notes(args.source_network, claim_info)
                success_count = sum(1 for v in results.values() if v)
                print(f"\n✓ Updated notes for {success_count}/{len(results)} devices")
                
            except Exception as e:
                print(f"\n✗ Failed to update device notes: {e}")
                return
        
        # Generate sample claim info file if neither tag nor claim info provided
        if not args.add_tag and not args.claim_info:
            devices = migrator.get_devices(args.source_network)
            sample_file = f"claim_info_template_{args.source_network}.json"
            
            sample_mapping = {}
            for device in devices:
                sample_mapping[device['serial']] = {
                    "name": device.get('name', ''),
                    "model": device.get('model', ''),
                    "order": "ENTER_ORDER_NUMBER",
                    "claim": "OR_ENTER_CLAIM_KEY"
                }
            
            with open(sample_file, 'w') as f:
                json.dump(sample_mapping, f, indent=2)
            
            print(f"\n✓ Generated claim info template: {sample_file}")
            print("\nTo use this template:")
            print("1. Edit the file and add order numbers or claim keys")
            print("2. Run: python meraki_migration.py --api-key KEY --mode prepare \\")
            print(f"        --source-network {args.source_network} --claim-info {sample_file}")
    
    # Inventory mode
    elif args.mode == "inventory":
        if not args.source_org or not args.source_network:
            parser.error("Inventory mode requires --source-org and --source-network")
        
        filename = f"inventory_{args.source_network}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report = migrator.generate_inventory_report(args.source_org, args.source_network, filename)
        
        print(f"\n✓ Inventory report generated!")
        print(f"  - JSON report: {filename}")
        print(f"  - CSV report: {filename.replace('.json', '.csv')}")
        print(f"\nSummary:")
        print(f"  - Total devices: {report['summary']['total_devices']}")
        print(f"  - Device models:")
        for model, count in report['summary']['device_models'].items():
            print(f"    - {model}: {count}")
    
    # Verify mode
    elif args.mode == "verify":
        if not args.backup_file or not args.target_org:
            parser.error("Verify mode requires --backup-file and --target-org")
        
        backup = migrator.load_backup(args.backup_file)
        device_serials = [d['serial'] for d in backup.get('devices', [])]
        
        print(f"\nVerifying devices in target organization...")
        device_status = migrator.verify_devices_in_target(args.target_org, device_serials)
        
        found = []
        missing = []
        
        for serial, is_found in device_status.items():
            device_name = next((d.get('name', 'Unnamed') for d in backup['devices'] 
                              if d['serial'] == serial), 'Unknown')
            if is_found:
                found.append(f"{serial} ({device_name})")
            else:
                missing.append(f"{serial} ({device_name})")
        
        print(f"\n✓ Found in target org ({len(found)}):")
        for device in found:
            print(f"  - {device}")
        
        if missing:
            print(f"\n✗ Missing from target org ({len(missing)}):")
            for device in missing:
                print(f"  - {device}")
        else:
            print("\n✓ All devices found in target organization!")
    
    # Wait mode
    elif args.mode == "wait":
        if not args.backup_file or not args.target_org:
            parser.error("Wait mode requires --backup-file and --target-org")
        
        backup = migrator.load_backup(args.backup_file)
        device_serials = [d['serial'] for d in backup.get('devices', [])]
        
        print(f"\nWaiting for {len(device_serials)} devices to appear in target organization...")
        print(f"Timeout: {args.timeout} seconds")
        print("Press Ctrl+C to stop waiting\n")
        
        try:
            success = migrator.wait_for_devices(
                args.target_org, 
                device_serials,
                args.target_network,
                timeout=args.timeout
            )
            
            if success:
                print("\n✓ All devices are ready!")
                if args.target_network:
                    print(f"  All devices added to network: {args.target_network}")
                    print("\nYou can now run restore with --device-mapping")
                else:
                    print("  All devices found in organization inventory")
                    print("\nNext steps:")
                    print("1. Create or specify target network")
                    print("2. Add devices to the network")
                    print("3. Run restore with --device-mapping")
            else:
                print("\n✗ Timeout reached. Check device status with --mode verify")
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
    
    # Restore mode
    elif args.mode == "restore":
        if not args.backup_file or not args.target_org:
            parser.error("Restore mode requires --backup-file and --target-org")
        
        backup = migrator.load_backup(args.backup_file)
        
        # Load device mapping if provided
        device_mapping = None
        if args.device_mapping:
            with open(args.device_mapping, 'r') as f:
                mapping_data = json.load(f)
                device_mapping = {k: v['new_serial'] for k, v in mapping_data.items() 
                                if v.get('new_serial') != "ENTER_NEW_SERIAL_HERE"}
        
        network_id = migrator.restore_network_settings(
            backup, 
            args.target_org, 
            args.target_network,
            device_mapping
        )
        print(f"\nSettings restored to network: {network_id}")
        
    # Migrate mode (backup + restore in one operation)
    elif args.mode == "migrate":
        if not all([args.source_org, args.source_network, args.target_org]):
            parser.error("Migrate mode requires --source-org, --source-network, and --target-org")
        
        # Backup
        logger.info("Phase 1: Backing up source network")
        backup = migrator.backup_network_settings(
            args.source_org, 
            args.source_network,
            include_org_settings=args.include_org_settings
        )
        
        # Save backup
        filename = f"meraki_migration_{args.source_network}_to_{args.target_org}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        migrator.save_backup(backup, filename)
        
        # Generate device mapping template
        mapping_file = filename.replace('.json', '_device_mapping.json')
        migrator.generate_device_mapping_template(backup, mapping_file)
        
        # Restore
        logger.info("Phase 2: Restoring to target organization")
        network_id = migrator.restore_network_settings(backup, args.target_org, args.target_network)
        
        print(f"\nMigration complete!")
        print(f"Backup saved to: {filename}")
        print(f"Device mapping template: {mapping_file}")
        print(f"New network ID: {network_id}")


if __name__ == "__main__":
    main()
