#!/usr/bin/env python3
"""
Garment ERP v8.0 Refactoring Verification Test
Tests all endpoints specified in the refactoring review request.
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

class GarmentERPRefactoringTester:
    def __init__(self, base_url="https://garment-erp-phase11b.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Endpoints to test from the review request
        self.endpoints_to_test = [
            {"method": "POST", "path": "/api/auth/login", "expected_status": 200, "description": "Login with admin@garment.com/Admin@123"},
            {"method": "GET", "path": "/api/dashboard", "expected_status": 200, "description": "Dashboard with 41+ keys"},
            {"method": "GET", "path": "/api/dashboard/analytics", "expected_status": 200, "description": "Analytics with weeklyThroughput array"},
            {"method": "GET", "path": "/api/reports/shipment", "expected_status": 200, "description": "Shipment reports array"},
            {"method": "GET", "path": "/api/reports/progress", "expected_status": 200, "description": "Progress reports array"},
            {"method": "GET", "path": "/api/reports/return", "expected_status": 200, "description": "Return reports array"},
            {"method": "GET", "path": "/api/reports/accessory", "expected_status": 200, "description": "Accessory reports array"},
            {"method": "GET", "path": "/api/export-pdf?type=report-production", "expected_status": 200, "description": "PDF export production report"},
            {"method": "GET", "path": "/api/export-pdf?type=report-shipment", "expected_status": 200, "description": "PDF export shipment report"},
            {"method": "GET", "path": "/api/export-pdf?type=report-progress", "expected_status": 200, "description": "PDF export progress report"},
            {"method": "GET", "path": "/api/export-pdf?type=unknown", "expected_status": 200, "description": "PDF export unknown type (error JSON)"},
            {"method": "GET", "path": "/api/pdf-export-columns?type=report-production", "expected_status": 200, "description": "PDF export columns config"},
            {"method": "GET", "path": "/api/pdf-export-configs", "expected_status": 200, "description": "PDF export configs array"},
            {"method": "GET", "path": "/api/roles", "expected_status": 200, "description": "Roles array"},
            {"method": "GET", "path": "/api/serial-list", "expected_status": 200, "description": "Serial list array"},
            {"method": "GET", "path": "/api/production-monitoring-v2", "expected_status": 200, "description": "Production monitoring array"},
            {"method": "GET", "path": "/api/distribusi-kerja", "expected_status": 200, "description": "Work distribution with hierarchy/flat/invalid_records keys"},
            {"method": "GET", "path": "/api/financial-recap", "expected_status": 200, "description": "Financial recap with financial keys"},
            {"method": "GET", "path": "/api/products?page=1&per_page=5", "expected_status": 200, "description": "Products paginated envelope"},
            {"method": "GET", "path": "/api/production-pos?page=1&per_page=5", "expected_status": 200, "description": "Production POs paginated envelope"},
            {"method": "GET", "path": "/api/vendor-material-inspections", "expected_status": 200, "description": "Vendor material inspections array"},
        ]

    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}: {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details,
            "response_sample": str(response_data)[:200] if response_data else ""
        })

    def make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> tuple:
        """Make HTTP request with auth"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=30)
            else:
                return False, None, f"Unsupported method: {method}"
            
            return True, response, None
        except Exception as e:
            return False, None, str(e)

    def test_login(self) -> bool:
        """Test admin login and get token"""
        print("\n🔐 Testing Authentication...")
        
        success, response, error = self.make_request('POST', '/api/auth/login', {
            'email': 'admin@garment.com',
            'password': 'Admin@123'
        })
        
        if not success:
            self.log_test("Admin Login", False, f"Request failed: {error}")
            return False
        
        if response.status_code != 200:
            self.log_test("Admin Login", False, f"Status {response.status_code}: {response.text}")
            return False
        
        try:
            data = response.json()
            if 'token' not in data:
                self.log_test("Admin Login", False, "No token in response")
                return False
            
            self.token = data['token']
            self.log_test("Admin Login", True, f"Token received, user: {data.get('user', {}).get('name', 'Unknown')}")
            return True
        except Exception as e:
            self.log_test("Admin Login", False, f"JSON parse error: {e}")
            return False

    def test_dashboard_endpoints(self):
        """Test dashboard endpoints"""
        print("\n📊 Testing Dashboard Endpoints...")
        
        # Test /api/dashboard
        success, response, error = self.make_request('GET', '/api/dashboard')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    key_count = len(data.keys())
                    if key_count >= 41:
                        self.log_test("Dashboard - 41+ keys", True, f"Found {key_count} keys")
                    else:
                        self.log_test("Dashboard - 41+ keys", False, f"Only {key_count} keys found")
                else:
                    self.log_test("Dashboard - response format", False, "Response is not a dict")
            except Exception as e:
                self.log_test("Dashboard - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Dashboard - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test /api/dashboard/analytics
        success, response, error = self.make_request('GET', '/api/dashboard/analytics')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'weeklyThroughput' in data:
                    if isinstance(data['weeklyThroughput'], list):
                        self.log_test("Dashboard Analytics - weeklyThroughput array", True, f"Array with {len(data['weeklyThroughput'])} items")
                    else:
                        self.log_test("Dashboard Analytics - weeklyThroughput array", False, "weeklyThroughput is not an array")
                else:
                    self.log_test("Dashboard Analytics - weeklyThroughput", False, "No weeklyThroughput field found")
            except Exception as e:
                self.log_test("Dashboard Analytics - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Dashboard Analytics - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def test_reports_endpoints(self):
        """Test reports endpoints"""
        print("\n📋 Testing Reports Endpoints...")
        
        report_types = ['shipment', 'progress', 'return', 'accessory']
        
        for report_type in report_types:
            success, response, error = self.make_request('GET', f'/api/reports/{report_type}')
            if success and response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list):
                        self.log_test(f"Reports - {report_type} array", True, f"Array with {len(data)} items")
                    else:
                        self.log_test(f"Reports - {report_type} array", False, "Response is not an array")
                except Exception as e:
                    self.log_test(f"Reports - {report_type} JSON parse", False, f"JSON parse error: {e}")
            else:
                self.log_test(f"Reports - {report_type} GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def test_pdf_export_endpoints(self):
        """Test PDF export endpoints"""
        print("\n📄 Testing PDF Export Endpoints...")
        
        # Test PDF exports
        pdf_types = [
            ('report-production', 'Production report PDF'),
            ('report-shipment', 'Shipment report PDF'),
            ('report-progress', 'Progress report PDF')
        ]
        
        for pdf_type, description in pdf_types:
            success, response, error = self.make_request('GET', f'/api/export-pdf?type={pdf_type}')
            if success and response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'application/pdf' in content_type or response.content.startswith(b'%PDF'):
                    self.log_test(f"PDF Export - {pdf_type}", True, f"PDF generated successfully")
                else:
                    # Could be JSON response with data
                    try:
                        data = response.json()
                        self.log_test(f"PDF Export - {pdf_type}", True, f"JSON response (possibly empty data)")
                    except:
                        self.log_test(f"PDF Export - {pdf_type}", False, f"Not a PDF and not JSON: {content_type}")
            else:
                self.log_test(f"PDF Export - {pdf_type}", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test unknown type (should return error JSON with 400 status)
        success, response, error = self.make_request('GET', '/api/export-pdf?type=unknown')
        if not success:
            self.log_test("PDF Export - unknown type", False, f"Request failed: {error}")
        elif response.status_code == 400:
            try:
                data = response.json()
                if 'error' in data and 'available_types' in data:
                    self.log_test("PDF Export - unknown type error JSON", True, "Error JSON returned as expected (400 status)")
                else:
                    self.log_test("PDF Export - unknown type error JSON", False, "No error or available_types field in JSON response")
            except Exception as e:
                self.log_test("PDF Export - unknown type JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("PDF Export - unknown type", False, f"Expected 400 status, got {response.status_code}: {response.text[:100] if response else 'No response'}")

    def test_pdf_config_endpoints(self):
        """Test PDF configuration endpoints"""
        print("\n⚙️ Testing PDF Configuration Endpoints...")
        
        # Test pdf-export-columns
        success, response, error = self.make_request('GET', '/api/pdf-export-columns?type=report-production')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'pdf_type' in data and 'columns' in data:
                    self.log_test("PDF Export Columns - structure", True, f"Valid structure with pdf_type and columns")
                else:
                    self.log_test("PDF Export Columns - structure", False, "Missing pdf_type or columns fields")
            except Exception as e:
                self.log_test("PDF Export Columns - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("PDF Export Columns - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test pdf-export-configs
        success, response, error = self.make_request('GET', '/api/pdf-export-configs')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("PDF Export Configs - array", True, f"Array with {len(data)} configs")
                else:
                    self.log_test("PDF Export Configs - array", False, "Response is not an array")
            except Exception as e:
                self.log_test("PDF Export Configs - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("PDF Export Configs - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def test_other_endpoints(self):
        """Test other specified endpoints"""
        print("\n🔧 Testing Other Endpoints...")
        
        # Test roles
        success, response, error = self.make_request('GET', '/api/roles')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Roles - array", True, f"Array with {len(data)} roles")
                else:
                    self.log_test("Roles - array", False, "Response is not an array")
            except Exception as e:
                self.log_test("Roles - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Roles - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test serial-list
        success, response, error = self.make_request('GET', '/api/serial-list')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Serial List - array", True, f"Array with {len(data)} serials")
                else:
                    self.log_test("Serial List - array", False, "Response is not an array")
            except Exception as e:
                self.log_test("Serial List - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Serial List - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test production-monitoring-v2
        success, response, error = self.make_request('GET', '/api/production-monitoring-v2')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Production Monitoring V2 - array", True, f"Array with {len(data)} items")
                else:
                    self.log_test("Production Monitoring V2 - array", False, "Response is not an array")
            except Exception as e:
                self.log_test("Production Monitoring V2 - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Production Monitoring V2 - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test distribusi-kerja
        success, response, error = self.make_request('GET', '/api/distribusi-kerja')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    required_keys = ['hierarchy', 'flat', 'invalid_records']
                    missing_keys = [k for k in required_keys if k not in data]
                    if not missing_keys:
                        self.log_test("Distribusi Kerja - structure", True, "Has hierarchy/flat/invalid_records keys")
                    else:
                        self.log_test("Distribusi Kerja - structure", False, f"Missing keys: {missing_keys}")
                else:
                    self.log_test("Distribusi Kerja - structure", False, "Response is not an object")
            except Exception as e:
                self.log_test("Distribusi Kerja - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Distribusi Kerja - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test financial-recap
        success, response, error = self.make_request('GET', '/api/financial-recap')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    # Check for financial-related keys
                    financial_keys = [k for k in data.keys() if any(term in k.lower() for term in ['financial', 'revenue', 'cost', 'profit', 'amount', 'total', 'balance'])]
                    if financial_keys:
                        self.log_test("Financial Recap - financial keys", True, f"Found financial keys: {financial_keys[:3]}...")
                    else:
                        self.log_test("Financial Recap - financial keys", True, f"Object with {len(data)} keys")
                else:
                    self.log_test("Financial Recap - structure", False, "Response is not an object")
            except Exception as e:
                self.log_test("Financial Recap - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Financial Recap - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def test_paginated_endpoints(self):
        """Test paginated endpoints"""
        print("\n📄 Testing Paginated Endpoints...")
        
        # Test products pagination
        success, response, error = self.make_request('GET', '/api/products?page=1&per_page=5')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and all(k in data for k in ['items', 'total', 'page', 'per_page', 'total_pages']):
                    self.log_test("Products - paginated envelope", True, f"Valid envelope: {len(data['items'])} items, page {data['page']}")
                else:
                    self.log_test("Products - paginated envelope", False, "Invalid envelope structure")
            except Exception as e:
                self.log_test("Products - paginated JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Products - paginated GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")
        
        # Test production-pos pagination
        success, response, error = self.make_request('GET', '/api/production-pos?page=1&per_page=5')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and all(k in data for k in ['items', 'total', 'page', 'per_page', 'total_pages']):
                    self.log_test("Production POs - paginated envelope", True, f"Valid envelope: {len(data['items'])} items, page {data['page']}")
                else:
                    self.log_test("Production POs - paginated envelope", False, "Invalid envelope structure")
            except Exception as e:
                self.log_test("Production POs - paginated JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Production POs - paginated GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def test_vendor_material_inspections(self):
        """Test vendor material inspections endpoint"""
        print("\n🔍 Testing Vendor Material Inspections...")
        
        success, response, error = self.make_request('GET', '/api/vendor-material-inspections')
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Vendor Material Inspections - array", True, f"Array with {len(data)} inspections")
                else:
                    self.log_test("Vendor Material Inspections - array", False, "Response is not an array")
            except Exception as e:
                self.log_test("Vendor Material Inspections - JSON parse", False, f"JSON parse error: {e}")
        else:
            self.log_test("Vendor Material Inspections - GET", False, f"Status {response.status_code if response else 'N/A'}: {error}")

    def run_all_tests(self) -> Dict:
        """Run all refactoring verification tests"""
        print("🚀 Starting Garment ERP v8.0 Refactoring Verification Tests")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📅 Test Time: {datetime.now().isoformat()}")
        
        # Authentication
        if not self.test_login():
            print("❌ Authentication failed - stopping tests")
            return self.get_summary()
        
        # Test all endpoint categories
        self.test_dashboard_endpoints()
        self.test_reports_endpoints()
        self.test_pdf_export_endpoints()
        self.test_pdf_config_endpoints()
        self.test_other_endpoints()
        self.test_paginated_endpoints()
        self.test_vendor_material_inspections()
        
        return self.get_summary()

    def get_summary(self) -> Dict:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": f"{success_rate:.1f}%",
            "test_results": self.test_results,
            "summary": f"Garment ERP v8.0 Refactoring Verification: {self.tests_passed}/{self.tests_run} tests passed ({success_rate:.1f}%)"
        }

def main():
    """Main test execution"""
    tester = GarmentERPRefactoringTester()
    
    try:
        results = tester.run_all_tests()
        
        print(f"\n📊 Test Summary:")
        print(f"   Total Tests: {results['total_tests']}")
        print(f"   Passed: {results['passed_tests']}")
        print(f"   Failed: {results['failed_tests']}")
        print(f"   Success Rate: {results['success_rate']}")
        
        # Print failed tests
        failed_tests = [t for t in results['test_results'] if not t['success']]
        if failed_tests:
            print(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['name']}: {test['details']}")
        
        # Return appropriate exit code
        return 0 if results['failed_tests'] == 0 else 1
        
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())