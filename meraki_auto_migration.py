#!/usr/bin/env python3
"""
Meraki Network Migration Tool with UI Automation
Automatically migrates devices between organizations using API and UI automation
"""

import json
import logging
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os
import tempfile
import shutil
import uuid
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'meraki_auto_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set specific loggers to WARNING to reduce noise
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("selenium").setLevel(logging.WARNING)


class MerakiAPIClient:
    """Handles all Meraki API operations"""
    
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
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                # Don't retry on 404s - feature not available
                if response.status_code == 404:
                    return None
                
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                return None
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Feature not available for this network/device
                    return None
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    
    def get_organizations(self) -> List[Dict]:
        """Get all organizations"""
        return self._api_call("GET", "/organizations")
    
    def get_org_name(self, org_id: str) -> str:
        """Get organization name"""
        orgs = self.get_organizations()
        for org in orgs:
            if org['id'] == org_id:
                return org['name']
        return "Unknown"
    
    def get_networks(self, org_id: str) -> List[Dict]:
        """Get all networks in an organization"""
        return self._api_call("GET", f"/organizations/{org_id}/networks")
    
    def get_network_info(self, network_id: str) -> Dict:
        """Get network information"""
        return self._api_call("GET", f"/networks/{network_id}")
    
    def get_devices(self, network_id: str) -> List[Dict]:
        """Get all devices in a network"""
        return self._api_call("GET", f"/networks/{network_id}/devices")
    
    def create_network(self, org_id: str, network_config: Dict) -> str:
        """Create a new network"""
        return self._api_call("POST", f"/organizations/{org_id}/networks", data=network_config)['id']
    
    def add_devices_to_network(self, network_id: str, serials: List[str]) -> bool:
        """Add devices to network"""
        try:
            self._api_call("POST", f"/networks/{network_id}/devices/claim", 
                          data={"serials": serials})
            return True
        except Exception as e:
            logger.error(f"Failed to add devices to network: {e}")
            return False


class ComprehensiveBackup:
    """Handles comprehensive backup of all network and device settings"""
    
    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client
    
    def backup_all_settings(self, org_id: str, network_id: str) -> Dict:
        """Backup all network and device settings comprehensively"""
        logger.info(f"Starting comprehensive backup for network {network_id}")
        
        backup = {
            "timestamp": datetime.now().isoformat(),
            "org_id": org_id,
            "org_name": self.api.get_org_name(org_id),
            "network_id": network_id,
            "network_info": {},
            "devices": [],
            "network_settings": {
                "switch": {},
                "routing": {},
                "security": {},
                "monitoring": {}
            },
            "device_settings": {}
        }
        
        # Get network info
        backup["network_info"] = self.api.get_network_info(network_id)
        logger.info("Backed up network info")
        
        # Get devices
        devices = self.api.get_devices(network_id)
        backup["devices"] = devices
        logger.info(f"Found {len(devices)} devices")
        
        # Backup network-level switch settings
        self._backup_switch_network_settings(network_id, backup["network_settings"]["switch"])
        
        # Backup routing settings
        self._backup_routing_settings(network_id, backup["network_settings"]["routing"])
        
        # Backup security settings
        self._backup_security_settings(network_id, backup["network_settings"]["security"])
        
        # Backup monitoring settings
        self._backup_monitoring_settings(network_id, backup["network_settings"]["monitoring"])
        
        # Backup device-specific settings
        for device in devices:
            serial = device['serial']
            backup["device_settings"][serial] = self._backup_device_settings(serial, device)
        
        # Log backup summary
        logger.info("=" * 50)
        logger.info("BACKUP SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Network: {backup['network_info'].get('name')} ({network_id})")
        logger.info(f"Devices: {len(devices)}")
        
        # Count backed up settings
        switch_count = sum(1 for v in backup["network_settings"]["switch"].values() if v)
        routing_count = sum(1 for v in backup["network_settings"]["routing"].values() if v)
        security_count = sum(1 for v in backup["network_settings"]["security"].values() if v)
        monitoring_count = sum(1 for v in backup["network_settings"]["monitoring"].values() if v)
        
        logger.info(f"Network Settings Backed Up:")
        logger.info(f"  - Switch settings: {switch_count}")
        logger.info(f"  - Routing settings: {routing_count}")
        logger.info(f"  - Security settings: {security_count}")
        logger.info(f"  - Monitoring settings: {monitoring_count}")
        
        port_count = sum(len(d.get("ports", [])) for d in backup["device_settings"].values())
        logger.info(f"Device Settings Backed Up:")
        logger.info(f"  - Total ports configured: {port_count}")
        logger.info("=" * 50)
        
        return backup
    
    def _backup_switch_network_settings(self, network_id: str, settings: Dict):
        """Backup switch-specific network settings"""
        endpoints = {
            "stp": f"/networks/{network_id}/switch/stp",
            "mtu": f"/networks/{network_id}/switch/mtu",
            "settings": f"/networks/{network_id}/switch/settings",
            "accessPolicies": f"/networks/{network_id}/switch/accessPolicies",
            "portSchedules": f"/networks/{network_id}/switch/portSchedules",
            "qosRules": f"/networks/{network_id}/switch/qosRules",
            "stormControl": f"/networks/{network_id}/switch/stormControl",
            "dhcpServerPolicy": f"/networks/{network_id}/switch/dhcpServerPolicy",
            "dscpToCosMappings": f"/networks/{network_id}/switch/dscp",
            "alternateManagementInterface": f"/networks/{network_id}/switch/alternateManagementInterface",
            "linkAggregations": f"/networks/{network_id}/switch/linkAggregations"
        }
        
        # Features that commonly return 404 (not available on all networks)
        optional_features = ["dscpToCosMappings", "linkAggregations", "alternateManagementInterface"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up switch {name}")
                elif name in optional_features:
                    logger.debug(f"Switch {name} not available on this network")
                else:
                    logger.info(f"Switch {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup switch {name}: {e}")
    
    def _backup_routing_settings(self, network_id: str, settings: Dict):
        """Backup routing settings"""
        endpoints = {
            "staticRoutes": f"/networks/{network_id}/appliance/staticRoutes",
            "ospf": f"/networks/{network_id}/switch/routing/ospf",
            "multicast": f"/networks/{network_id}/switch/routing/multicast",
            "warmSpare": f"/networks/{network_id}/switch/warmSpare"
        }
        
        # Features that commonly return 404
        optional_features = ["warmSpare", "ospf"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up routing {name}")
                elif name in optional_features:
                    logger.debug(f"Routing {name} not available on this network")
                else:
                    logger.info(f"Routing {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup routing {name}: {e}")
    
    def _backup_security_settings(self, network_id: str, settings: Dict):
        """Backup security settings including ACLs"""
        endpoints = {
            "accessControlLists": f"/networks/{network_id}/switch/accessControlLists",
            "portSecurity": f"/networks/{network_id}/switch/portSecurity",
            "stpGuard": f"/networks/{network_id}/switch/stpGuard"
        }
        
        # Features that commonly return 404 (newer features)
        optional_features = ["portSecurity", "stpGuard"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up security {name}")
                elif name in optional_features:
                    logger.debug(f"Security {name} not available on this network")
                else:
                    logger.info(f"Security {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup security {name}: {e}")
    
    def _backup_monitoring_settings(self, network_id: str, settings: Dict):
        """Backup monitoring settings"""
        endpoints = {
            "snmp": f"/networks/{network_id}/snmp",
            "syslog": f"/networks/{network_id}/syslogServers",
            "netflow": f"/networks/{network_id}/netflow",
            "alerts": f"/networks/{network_id}/alerts/settings"
        }
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up monitoring {name}")
                else:
                    logger.info(f"Monitoring {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup monitoring {name}: {e}")
    
    def _backup_device_settings(self, serial: str, device_info: Dict) -> Dict:
        """Backup all device-specific settings"""
        device_name = device_info.get('name', 'Unnamed')
        logger.info(f"Backing up device {serial} ({device_name})")
        
        settings = {
            "info": device_info,
            "ports": [],
            "management": {},
            "routing": {},
            "dhcp": {}
        }
        
        # Management interface (includes IP settings)
        try:
            result = self.api._api_call("GET", f"/devices/{serial}/managementInterface")
            if result is not None:
                settings["management"] = result
            else:
                logger.debug(f"No management interface configured for {serial}")
        except Exception as e:
            if "404" not in str(e):
                logger.warning(f"Could not backup management interface for {serial}: {e}")
        
        # Switch ports (all port-level settings)
        if device_info.get('model', '').startswith('MS'):
            try:
                ports = self.api._api_call("GET", f"/devices/{serial}/switch/ports")
                if ports is not None:
                    settings["ports"] = ports
                    logger.info(f"Backed up {len(ports)} ports for {serial}")
                else:
                    logger.info(f"No port configuration for {serial}")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup ports for {serial}: {e}")
            
            # Routing interfaces (Layer 3) - only for L3 switches
            try:
                interfaces = self.api._api_call("GET", f"/devices/{serial}/switch/routing/interfaces")
                if interfaces is not None:
                    settings["routing"]["interfaces"] = interfaces
                    logger.debug(f"Backed up routing interfaces for {serial}")
            except Exception:
                pass  # Not all switches support L3
            
            # Static routes - only for L3 switches
            try:
                routes = self.api._api_call("GET", f"/devices/{serial}/switch/routing/staticRoutes")
                if routes is not None:
                    settings["routing"]["staticRoutes"] = routes
                    logger.debug(f"Backed up static routes for {serial}")
            except Exception:
                pass  # Not all switches support L3
            
            # DHCP settings - only for L3 switches
            try:
                dhcp = self.api._api_call("GET", f"/devices/{serial}/switch/dhcp/v4/servers")
                if dhcp is not None:
                    settings["dhcp"]["subnets"] = dhcp
                    logger.debug(f"Backed up DHCP settings for {serial}")
            except Exception:
                pass  # Not all switches support DHCP server
        
        return settings


class MerakiUIAutomation:
    """Handles UI automation for device unclaim/claim operations"""
    
    def __init__(self, username: str, password: str, headless: bool = False):
        self.username = username
        self.password = password
        self.driver = None
        self.wait = None
        self.headless = headless
        self.temp_dir = None
        
    def __enter__(self):
        self.setup_driver()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()
        if self.temp_dir:
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
    
    def kill_chrome_processes(self):
        """Kill any existing Chrome/ChromeDriver processes"""
        try:
            # More aggressive cleanup
            chrome_processes = [
                'chrome', 'chromium', 'google-chrome', 'google-chrome-stable',
                'chromedriver', 'chromium-browser'
            ]
            
            for process in chrome_processes:
                subprocess.run(['pkill', '-9', '-f', process], capture_output=True)
            
            # Also try killall
            subprocess.run(['killall', '-9', 'chrome'], capture_output=True, stderr=subprocess.DEVNULL)
            subprocess.run(['killall', '-9', 'chromedriver'], capture_output=True, stderr=subprocess.DEVNULL)
            
            # Clean up any stale Chrome directories
            import glob
            temp_dirs = glob.glob('/tmp/.com.google.Chrome.*')
            temp_dirs.extend(glob.glob('/tmp/chrome*'))
            temp_dirs.extend(glob.glob('/tmp/meraki_chrome*'))
            
            for temp_dir in temp_dirs:
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
            
            time.sleep(3)  # Give processes time to die
            logger.info("Cleaned up existing Chrome processes and directories")
            
        except Exception as e:
            logger.warning(f"Could not kill Chrome processes: {e}")
    
    def setup_driver(self):
        """Setup Chrome driver with options"""
        # Kill any existing Chrome processes first
        self.kill_chrome_processes()
        
        options = webdriver.ChromeOptions()
        
        # Create unique user data directory to avoid conflicts
        self.temp_dir = os.path.join(tempfile.gettempdir(), f'meraki_chrome_{uuid.uuid4()}')
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Essential options
        options.add_argument(f'--user-data-dir={self.temp_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-setuid-sandbox')
        
        # Headless mode if requested
        if self.headless:
            options.add_argument('--headless=new')
            logger.info("Running Chrome in HEADLESS mode")
        else:
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
        
        # Additional stability options
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        logger.info(f"Using temp directory: {self.temp_dir}")
        
        # Try to find chromedriver in common locations
        chromedriver_paths = [
            '/usr/bin/chromedriver',
            '/usr/local/bin/chromedriver',
            'chromedriver',
            './chromedriver'
        ]
        
        chromedriver_path = None
        for path in chromedriver_paths:
            if os.path.exists(path) or shutil.which(path):
                chromedriver_path = path
                logger.info(f"Found ChromeDriver at: {chromedriver_path}")
                break
        
        try:
            if chromedriver_path:
                from selenium.webdriver.chrome.service import Service
                service = Service(chromedriver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
                
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("Chrome driver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            logger.error("Make sure Chrome and ChromeDriver are installed:")
            logger.error("  sudo apt-get install google-chrome-stable chromium-chromedriver")
            raise
    
    def login(self):
        """Login to Meraki Dashboard"""
        logger.info("Logging into Meraki Dashboard")
        self.driver.get("https://dashboard.meraki.com")
        
        # Enter username
        username_field = self.wait.until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        username_field.send_keys(self.username)
        username_field.send_keys(Keys.RETURN)
        
        # Wait and enter password
        time.sleep(2)
        password_field = self.wait.until(
            EC.presence_of_element_located((By.ID, "password"))
        )
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)
        
        # Wait for dashboard to load
        self.wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "main-navigation"))
        )
        logger.info("Successfully logged in")
        time.sleep(3)
    
    def select_organization(self, org_name: str):
        """Select organization by name"""
        logger.info(f"Selecting organization: {org_name}")
        
        # Click org selector
        org_selector = self.wait.until(
            EC.element_to_be_clickable((By.CLASS_NAME, "org-selector"))
        )
        org_selector.click()
        
        # Find and click org
        time.sleep(1)
        org_elements = self.driver.find_elements(By.CLASS_NAME, "org-name")
        for elem in org_elements:
            if org_name.lower() in elem.text.lower():
                elem.click()
                logger.info(f"Selected organization: {org_name}")
                time.sleep(3)
                return
        
        raise Exception(f"Organization '{org_name}' not found")
    
    def unclaim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Unclaim devices from organization"""
        try:
            self.select_organization(org_name)
            
            # Navigate to inventory
            logger.info("Navigating to Organization > Inventory")
            org_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Organization']"))
            )
            org_menu.click()
            
            inventory_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
            )
            inventory_link.click()
            
            time.sleep(3)
            
            # Search and select devices
            for serial in device_serials:
                logger.info(f"Selecting device {serial}")
                
                # Search for device
                search_box = self.wait.until(
                    EC.presence_of_element_located((By.CLASS_NAME, "search-box"))
                )
                search_box.clear()
                search_box.send_keys(serial)
                search_box.send_keys(Keys.RETURN)
                
                time.sleep(2)
                
                # Select device checkbox
                checkbox = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//tr[contains(.,'{serial}')]//input[@type='checkbox']"))
                )
                checkbox.click()
            
            # Click remove button
            logger.info("Removing devices from organization")
            remove_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Remove')]"))
            )
            remove_btn.click()
            
            # Confirm removal
            confirm_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Remove from organization')]"))
            )
            confirm_btn.click()
            
            logger.info(f"Successfully unclaimed {len(device_serials)} devices")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unclaim devices: {e}")
            return False
    
    def claim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Claim devices in organization"""
        try:
            self.select_organization(org_name)
            
            # Navigate to inventory
            logger.info("Navigating to Organization > Inventory")
            org_menu = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Organization']"))
            )
            org_menu.click()
            
            inventory_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
            )
            inventory_link.click()
            
            time.sleep(3)
            
            # Click claim button
            claim_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Claim')]"))
            )
            claim_btn.click()
            
            # Enter serials
            logger.info(f"Claiming {len(device_serials)} devices")
            serials_field = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//textarea[@placeholder='Enter serials']"))
            )
            serials_field.send_keys('\n'.join(device_serials))
            
            # Submit claim
            submit_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Claim')]"))
            )
            submit_btn.click()
            
            # Wait for success
            time.sleep(5)
            
            logger.info(f"Successfully claimed {len(device_serials)} devices")
            return True
            
        except Exception as e:
            logger.error(f"Failed to claim devices: {e}")
            return False


class ComprehensiveRestore:
    """Handles restoration of all settings"""
    
    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client
    
    def restore_all_settings(self, backup: Dict, target_network_id: str, device_mapping: Optional[Dict] = None):
        """Restore all settings from backup"""
        logger.info(f"Starting comprehensive restore to network {target_network_id}")
        logger.info("=" * 50)
        
        # Restore network-level settings
        self._restore_network_settings(backup["network_settings"], target_network_id)
        
        # Restore device-specific settings
        if device_mapping:
            self._restore_device_settings(backup["device_settings"], device_mapping)
        else:
            logger.warning("No device mapping provided, skipping device-specific settings")
        
        logger.info("=" * 50)
        logger.info("RESTORE COMPLETE")
        logger.info("=" * 50)
        logger.info("Please verify the following in the Dashboard:")
        logger.info("  1. All network settings are properly configured")
        logger.info("  2. Device management IPs are correct")
        logger.info("  3. Port configurations match expectations")
        logger.info("  4. Any stack configurations are properly restored")
        logger.info("=" * 50)
    
    def _restore_network_settings(self, settings: Dict, network_id: str):
        """Restore network-level settings"""
        logger.info("Restoring network-level settings...")
        restored_count = 0
        
        # Restore switch settings
        switch_settings = settings.get("switch", {})
        
        # STP
        if switch_settings.get("stp"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/stp", 
                                  data=switch_settings["stp"])
                logger.info("Restored STP settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore STP: {e}")
        
        # MTU
        if switch_settings.get("mtu"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/mtu", 
                                  data=switch_settings["mtu"])
                logger.info("Restored MTU settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore MTU: {e}")
        
        # DHCP Server Policy
        if switch_settings.get("dhcpServerPolicy"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/dhcpServerPolicy", 
                                  data=switch_settings["dhcpServerPolicy"])
                logger.info("Restored DHCP server policy")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore DHCP server policy: {e}")
        
        # Storm Control
        if switch_settings.get("stormControl"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/stormControl", 
                                  data=switch_settings["stormControl"])
                logger.info("Restored storm control settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore storm control: {e}")
        
        # Access Policies
        if switch_settings.get("accessPolicies"):
            try:
                for policy in switch_settings["accessPolicies"]:
                    policy_data = {k: v for k, v in policy.items() if k != "accessPolicyNumber"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/accessPolicies", 
                                      data=policy_data)
                logger.info(f"Restored {len(switch_settings['accessPolicies'])} access policies")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore access policies: {e}")
        
        # QoS Rules
        if switch_settings.get("qosRules"):
            try:
                for rule in switch_settings["qosRules"]:
                    rule_data = {k: v for k, v in rule.items() if k != "id"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/qosRules", 
                                      data=rule_data)
                logger.info(f"Restored {len(switch_settings['qosRules'])} QoS rules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore QoS rules: {e}")
        
        # Port Schedules
        if switch_settings.get("portSchedules"):
            try:
                for schedule in switch_settings["portSchedules"]:
                    schedule_data = {k: v for k, v in schedule.items() if k != "id"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/portSchedules", 
                                      data=schedule_data)
                logger.info(f"Restored {len(switch_settings['portSchedules'])} port schedules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore port schedules: {e}")
        
        # Monitoring settings
        monitoring_settings = settings.get("monitoring", {})
        
        # SNMP
        if monitoring_settings.get("snmp"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/snmp", 
                                  data=monitoring_settings["snmp"])
                logger.info("Restored SNMP settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore SNMP: {e}")
        
        # Syslog
        if monitoring_settings.get("syslog"):
            try:
                for server in monitoring_settings["syslog"]:
                    self.api._api_call("POST", f"/networks/{network_id}/syslogServers", 
                                      data=server)
                logger.info(f"Restored {len(monitoring_settings['syslog'])} syslog servers")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore syslog servers: {e}")
        
        # Alerts
        if monitoring_settings.get("alerts"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/alerts/settings", 
                                  data=monitoring_settings["alerts"])
                logger.info("Restored alert settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore alerts: {e}")
        
        logger.info(f"Restored {restored_count} network-level settings")
    
    def _restore_device_settings(self, device_settings: Dict, device_mapping: Dict):
        """Restore device-specific settings"""
        logger.info(f"Restoring device-specific settings for {len(device_mapping)} devices...")
        
        for old_serial, new_serial in device_mapping.items():
            if old_serial not in device_settings:
                logger.warning(f"No settings found for device {old_serial}")
                continue
            
            settings = device_settings[old_serial]
            device_name = settings.get("info", {}).get("name", "Unnamed")
            logger.info(f"Restoring settings for device {new_serial} ({device_name})")
            
            restored_items = 0
            
            # Restore management interface
            if settings.get("management"):
                try:
                    mgmt_data = {k: v for k, v in settings["management"].items() 
                               if k not in ["ddnsHostnames", "wan1", "wan2"]}
                    self.api._api_call("PUT", f"/devices/{new_serial}/managementInterface", 
                                      data=mgmt_data)
                    logger.info(f"  ✓ Restored management interface for {new_serial}")
                    restored_items += 1
                except Exception as e:
                    logger.error(f"  ✗ Failed to restore management interface: {e}")
            
            # Restore switch ports
            if settings.get("ports"):
                successful_ports = 0
                failed_ports = 0
                
                for port in settings["ports"]:
                    port_id = port["portId"]
                    port_data = {k: v for k, v in port.items() 
                               if k not in ["portId", "warnings", "errors", "status", "speed", "duplex", 
                                          "usageInKbps", "cdp", "lldp", "clientCount", "powerUsageInWh"]}
                    
                    try:
                        self.api._api_call("PUT", f"/devices/{new_serial}/switch/ports/{port_id}", 
                                          data=port_data)
                        successful_ports += 1
                    except Exception as e:
                        failed_ports += 1
                        logger.debug(f"Failed to restore port {port_id}: {e}")
                
                if successful_ports > 0:
                    logger.info(f"  ✓ Restored {successful_ports} ports for {new_serial}")
                    restored_items += successful_ports
                if failed_ports > 0:
                    logger.warning(f"  ⚠ Failed to restore {failed_ports} ports for {new_serial}")
            
            logger.info(f"  Completed restoration for {new_serial}: {restored_items} items restored")


class AutomatedMigrationTool:
    """Main tool for automated migration"""
    
    def __init__(self, api_key: str, username: str, password: str, headless: bool = False):
        self.api = MerakiAPIClient(api_key)
        self.username = username
        self.password = password
        self.headless = headless
        self.backup_tool = ComprehensiveBackup(self.api)
        self.restore_tool = ComprehensiveRestore(self.api)
    
    def execute_migration(self, source_org_id: str, source_network_id: str, 
                         target_org_id: str, target_network_name: Optional[str] = None):
        """Execute complete automated migration"""
        
        # Step 1: Comprehensive backup
        logger.info("=" * 50)
        logger.info("STEP 1: Backing up all settings")
        logger.info("=" * 50)
        
        backup = self.backup_tool.backup_all_settings(source_org_id, source_network_id)
        
        # Save backup
        backup_file = f"migration_backup_{source_network_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup, f, indent=2)
        logger.info(f"Backup saved to {backup_file}")
        
        # Get device serials
        device_serials = [d['serial'] for d in backup['devices']]
        logger.info(f"Found {len(device_serials)} devices to migrate")
        
        # Step 2: UI Automation - Unclaim and Claim
        logger.info("=" * 50)
        logger.info("STEP 2: Moving devices via UI automation")
        logger.info("=" * 50)
        
        source_org_name = backup['org_name']
        target_org_name = self.api.get_org_name(target_org_id)
        
        with MerakiUIAutomation(self.username, self.password, self.headless) as ui:
            ui.login()
            
            # Unclaim from source
            logger.info(f"Unclaiming devices from {source_org_name}")
            if not ui.unclaim_devices(source_org_name, device_serials):
                raise Exception("Failed to unclaim devices")
            
            # Wait for unclaim to process
            logger.info("Waiting 120 seconds for unclaim to process...")
            time.sleep(120)
            
            # Claim in target
            logger.info(f"Claiming devices in {target_org_name}")
            if not ui.claim_devices(target_org_name, device_serials):
                raise Exception("Failed to claim devices")
        
        # Wait for claim to process
        logger.info("Waiting 30 seconds for claim to process...")
        time.sleep(30)
        
        # Step 3: Create network and add devices
        logger.info("=" * 50)
        logger.info("STEP 3: Creating network and adding devices")
        logger.info("=" * 50)
        
        # Create network
        network_name = target_network_name or f"{backup['network_info']['name']}_migrated"
        network_config = {
            "name": network_name,
            "productTypes": backup['network_info'].get('productTypes', ['switch']),
            "timeZone": backup['network_info'].get('timeZone', 'America/Los_Angeles')
        }
        
        target_network_id = self.api.create_network(target_org_id, network_config)
        logger.info(f"Created network: {target_network_id}")
        
        # Add devices to network
        if self.api.add_devices_to_network(target_network_id, device_serials):
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
        
        self.restore_tool.restore_all_settings(backup, target_network_id, device_mapping)
        
        logger.info("=" * 50)
        logger.info("MIGRATION COMPLETE!")
        logger.info(f"Target Network ID: {target_network_id}")
        logger.info("=" * 50)
        
        return target_network_id


def main():
    parser = argparse.ArgumentParser(description="Automated Meraki Migration Tool")
    parser.add_argument("--api-key", required=True, help="Meraki API key")
    parser.add_argument("--username", required=True, help="Meraki Dashboard username")
    parser.add_argument("--password", required=True, help="Meraki Dashboard password")
    parser.add_argument("--source-org", required=True, help="Source organization ID")
    parser.add_argument("--source-network", required=True, help="Source network ID")
    parser.add_argument("--target-org", required=True, help="Target organization ID")
    parser.add_argument("--target-network-name", help="Target network name (optional)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode (for servers)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Mask password in logs
    logger.info(f"Starting migration with user: {args.username}")
    if args.headless:
        logger.info("Running in HEADLESS mode")
    
    try:
        tool = AutomatedMigrationTool(args.api_key, args.username, args.password, args.headless)
        tool.execute_migration(
            args.source_org,
            args.source_network,
            args.target_org,
            args.target_network_name
        )
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    main()
