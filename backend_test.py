#!/usr/bin/env python3
"""
Phase 10A Backend Pagination Testing
Tests backward-compatible pagination implementation for ~20 list endpoints
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

class Phase10APaginationTester:
    def __init__(self, base_url="https://erp-production-track.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Endpoints to test for pagination
        self.pagination_endpoints = [
            "/api/production-pos",
            "/api/vendor-shipments", 
            "/api/buyer-shipments",
            "/api/invoices",
            "/api/payments",
            "/api/products",
            "/api/garments",
            "/api/product-variants",
            "/api/buyers",
            "/api/users",
            "/api/activity-logs",
            "/api/material-requests",
            "/api/production-returns",
            "/api/production-jobs",
            "/api/work-orders",
            "/api/accounts-payable",
            "/api/accounts-receivable",
            "/api/material-defect-reports",
            "/api/invoice-edit-requests"
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

    def test_backward_compatibility(self) -> None:
        """Test that endpoints without pagination params return arrays"""
        print("\n📋 Testing Backward Compatibility (Legacy Array Response)...")
        
        for endpoint in self.pagination_endpoints:
            success, response, error = self.make_request('GET', endpoint)
            
            if not success:
                self.log_test(f"Legacy Array {endpoint}", False, f"Request failed: {error}")
                continue
            
            if response.status_code != 200:
                self.log_test(f"Legacy Array {endpoint}", False, f"Status {response.status_code}")
                continue
            
            try:
                data = response.json()
                
                # Should be an array, not an envelope
                if isinstance(data, list):
                    self.log_test(f"Legacy Array {endpoint}", True, f"Returns array with {len(data)} items")
                elif isinstance(data, dict) and 'items' in data:
                    self.log_test(f"Legacy Array {endpoint}", False, "Returns envelope instead of array")
                else:
                    self.log_test(f"Legacy Array {endpoint}", False, f"Unexpected response type: {type(data)}")
                    
            except Exception as e:
                self.log_test(f"Legacy Array {endpoint}", False, f"JSON parse error: {e}")

    def test_paginated_envelope(self) -> None:
        """Test that endpoints with pagination params return envelope format"""
        print("\n📦 Testing Paginated Envelope Response...")
        
        for endpoint in self.pagination_endpoints:
            params = {'page': 1, 'per_page': 5}
            success, response, error = self.make_request('GET', endpoint, params=params)
            
            if not success:
                self.log_test(f"Paginated Envelope {endpoint}", False, f"Request failed: {error}")
                continue
            
            if response.status_code != 200:
                self.log_test(f"Paginated Envelope {endpoint}", False, f"Status {response.status_code}")
                continue
            
            try:
                data = response.json()
                
                # Should be an envelope with required fields
                if isinstance(data, dict):
                    required_fields = ['items', 'total', 'page', 'per_page', 'total_pages']
                    missing_fields = [f for f in required_fields if f not in data]
                    
                    if not missing_fields:
                        # Validate field types and values
                        if (isinstance(data['items'], list) and 
                            isinstance(data['total'], int) and
                            data['page'] == 1 and
                            data['per_page'] == 5 and
                            isinstance(data['total_pages'], int)):
                            self.log_test(f"Paginated Envelope {endpoint}", True, 
                                        f"Valid envelope: {len(data['items'])} items, total: {data['total']}")
                        else:
                            self.log_test(f"Paginated Envelope {endpoint}", False, "Invalid field types or values")
                    else:
                        self.log_test(f"Paginated Envelope {endpoint}", False, f"Missing fields: {missing_fields}")
                else:
                    self.log_test(f"Paginated Envelope {endpoint}", False, "Response is not an object")
                    
            except Exception as e:
                self.log_test(f"Paginated Envelope {endpoint}", False, f"JSON parse error: {e}")

    def test_per_page_cap(self) -> None:
        """Test that per_page is capped at 200"""
        print("\n🔒 Testing per_page Cap (max 200)...")
        
        # Test with production-pos endpoint
        params = {'page': 1, 'per_page': 500}  # Request more than cap
        success, response, error = self.make_request('GET', '/api/production-pos', params=params)
        
        if not success:
            self.log_test("per_page Cap Test", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("per_page Cap Test", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, dict) and 'per_page' in data:
                if data['per_page'] <= 200:
                    self.log_test("per_page Cap Test", True, f"per_page capped at {data['per_page']}")
                else:
                    self.log_test("per_page Cap Test", False, f"per_page not capped: {data['per_page']}")
            else:
                self.log_test("per_page Cap Test", False, "No per_page field in response")
        except Exception as e:
            self.log_test("per_page Cap Test", False, f"JSON parse error: {e}")

    def test_filters_preserved(self) -> None:
        """Test that existing filter parameters still work"""
        print("\n🔍 Testing Filter Preservation...")
        
        # Test production-pos with search and status filters
        params = {'search': 'TEST', 'status': 'Draft'}
        success, response, error = self.make_request('GET', '/api/production-pos', params=params)
        
        if success and response.status_code == 200:
            self.log_test("Filters - production-pos search+status", True, "Filters work without pagination")
        else:
            self.log_test("Filters - production-pos search+status", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test with pagination + filters
        params = {'search': 'TEST', 'status': 'Draft', 'page': 1, 'per_page': 10}
        success, response, error = self.make_request('GET', '/api/production-pos', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'items' in data:
                    self.log_test("Filters - production-pos with pagination", True, "Filters work with pagination")
                else:
                    self.log_test("Filters - production-pos with pagination", False, "Invalid response format")
            except:
                self.log_test("Filters - production-pos with pagination", False, "JSON parse error")
        else:
            self.log_test("Filters - production-pos with pagination", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test invoices with category filter
        params = {'category': 'VENDOR'}
        success, response, error = self.make_request('GET', '/api/invoices', params=params)
        
        if success and response.status_code == 200:
            self.log_test("Filters - invoices category", True, "Invoice category filter works")
        else:
            self.log_test("Filters - invoices category", False, f"Status {response.status_code if response else 'N/A'}")

    def test_sort_params(self) -> None:
        """Test sort_by and sort_dir parameters"""
        print("\n🔄 Testing Sort Parameters...")
        
        # Test activity-logs with sort
        params = {'page': 1, 'per_page': 3, 'sort_by': 'timestamp', 'sort_dir': 'asc'}
        success, response, error = self.make_request('GET', '/api/activity-logs', params=params)
        
        if not success:
            self.log_test("Sort Parameters - activity-logs", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Sort Parameters - activity-logs", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, dict) and 'items' in data and len(data['items']) >= 2:
                # Check if items are sorted by timestamp ascending
                items = data['items']
                timestamps = [item.get('timestamp') for item in items if item.get('timestamp')]
                
                if len(timestamps) >= 2:
                    # Simple check - first timestamp should be <= second timestamp for asc order
                    if timestamps[0] <= timestamps[1]:
                        self.log_test("Sort Parameters - activity-logs", True, "Ascending sort works")
                    else:
                        self.log_test("Sort Parameters - activity-logs", False, "Sort order incorrect")
                else:
                    self.log_test("Sort Parameters - activity-logs", True, "Sort params accepted (insufficient data to verify order)")
            else:
                self.log_test("Sort Parameters - activity-logs", True, "Sort params accepted")
        except Exception as e:
            self.log_test("Sort Parameters - activity-logs", False, f"JSON parse error: {e}")

    def test_legacy_limit_param(self) -> None:
        """Test legacy ?limit=N parameter for activity-logs"""
        print("\n⏮️ Testing Legacy limit Parameter...")
        
        params = {'limit': 5}
        success, response, error = self.make_request('GET', '/api/activity-logs', params=params)
        
        if not success:
            self.log_test("Legacy limit Parameter", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Legacy limit Parameter", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, list):
                if len(data) <= 5:
                    self.log_test("Legacy limit Parameter", True, f"Returns array with {len(data)} items (≤5)")
                else:
                    self.log_test("Legacy limit Parameter", False, f"Returns {len(data)} items (>5)")
            else:
                self.log_test("Legacy limit Parameter", False, "Does not return array")
        except Exception as e:
            self.log_test("Legacy limit Parameter", False, f"JSON parse error: {e}")

    def test_buyers_legacy_pagination(self) -> None:
        """Test buyers legacy ?paginated=true&page=1&limit=5 parameter"""
        print("\n⏮️ Testing Buyers Legacy Pagination...")
        
        params = {'paginated': 'true', 'page': 1, 'limit': 5}
        success, response, error = self.make_request('GET', '/api/buyers', params=params)
        
        if not success:
            self.log_test("Buyers Legacy Pagination", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Buyers Legacy Pagination", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, dict):
                # Should have legacy format with data, total, page, limit
                required_fields = ['data', 'total', 'page', 'limit']
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    self.log_test("Buyers Legacy Pagination", True, f"Legacy format: {len(data.get('data', []))} items")
                else:
                    self.log_test("Buyers Legacy Pagination", False, f"Missing legacy fields: {missing_fields}")
            else:
                self.log_test("Buyers Legacy Pagination", False, "Does not return dict")
        except Exception as e:
            self.log_test("Buyers Legacy Pagination", False, f"JSON parse error: {e}")

    def test_core_crud_operations(self) -> None:
        """Test core CRUD operations and data integrity"""
        print("\n🔧 Testing Core CRUD Operations...")
        
        # Test GET /api/production-pos and verify enriched fields
        success, response, error = self.make_request('GET', '/api/production-pos')
        
        if not success:
            self.log_test("Core CRUD - production-pos GET", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Core CRUD - production-pos GET", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                # Check first PO for required enriched fields
                po = data[0]
                required_fields = [
                    'items', 'item_count', 'total_qty', 'total_shipped_to_buyer',
                    'remaining_qty_to_ship', 'over_shipped_qty', 'total_sent_to_vendor',
                    'remaining_qty_to_vendor', 'serial_numbers', 'composite_label',
                    'po_accessories', 'po_accessories_count'
                ]
                
                missing_fields = [f for f in required_fields if f not in po]
                
                if not missing_fields:
                    self.log_test("Core CRUD - production-pos enriched fields", True, 
                                f"All enriched fields present in PO: {po.get('po_number', 'Unknown')}")
                else:
                    self.log_test("Core CRUD - production-pos enriched fields", False, 
                                f"Missing fields: {missing_fields}")
            else:
                self.log_test("Core CRUD - production-pos GET", True, "Empty list returned")
                
        except Exception as e:
            self.log_test("Core CRUD - production-pos GET", False, f"JSON parse error: {e}")

    def test_n1_regression_guard(self) -> None:
        """Test that response data shapes are unchanged (N+1 regression guard)"""
        print("\n🛡️ Testing N+1 Regression Guard...")
        
        # Test vendor-shipments response shape
        success, response, error = self.make_request('GET', '/api/vendor-shipments')
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    shipment = data[0]
                    required_fields = ['items', 'child_shipment_count', 'has_children', 'po_accessories_count']
                    missing_fields = [f for f in required_fields if f not in shipment]
                    
                    if not missing_fields:
                        self.log_test("N+1 Guard - vendor-shipments shape", True, "All required fields present")
                    else:
                        self.log_test("N+1 Guard - vendor-shipments shape", False, f"Missing: {missing_fields}")
                else:
                    self.log_test("N+1 Guard - vendor-shipments shape", True, "Empty list (shape preserved)")
            except Exception as e:
                self.log_test("N+1 Guard - vendor-shipments shape", False, f"JSON parse error: {e}")
        else:
            self.log_test("N+1 Guard - vendor-shipments shape", False, f"Request failed")
        
        # Test buyer-shipments response shape
        success, response, error = self.make_request('GET', '/api/buyer-shipments')
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    shipment = data[0]
                    required_fields = ['items', 'total_ordered', 'total_shipped', 'remaining', 'progress_pct', 'dispatch_count']
                    missing_fields = [f for f in required_fields if f not in shipment]
                    
                    if not missing_fields:
                        self.log_test("N+1 Guard - buyer-shipments shape", True, "All required fields present")
                    else:
                        self.log_test("N+1 Guard - buyer-shipments shape", False, f"Missing: {missing_fields}")
                else:
                    self.log_test("N+1 Guard - buyer-shipments shape", True, "Empty list (shape preserved)")
            except Exception as e:
                self.log_test("N+1 Guard - buyer-shipments shape", False, f"JSON parse error: {e}")
        else:
            self.log_test("N+1 Guard - buyer-shipments shape", False, f"Request failed")

    def test_production_jobs_enriched_fields(self) -> None:
        """Test production-jobs enriched fields"""
        print("\n🏭 Testing Production Jobs Enriched Fields...")
        
        success, response, error = self.make_request('GET', '/api/production-jobs')
        
        if not success:
            self.log_test("Production Jobs Enriched Fields", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Production Jobs Enriched Fields", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                job = data[0]
                required_fields = [
                    'item_count', 'total_ordered', 'total_available', 'total_produced',
                    'total_shipped_to_buyer', 'remaining_to_ship', 'progress_pct',
                    'serial_numbers', 'child_job_count', 'child_jobs'
                ]
                
                missing_fields = [f for f in required_fields if f not in job]
                
                if not missing_fields:
                    self.log_test("Production Jobs Enriched Fields", True, "All enriched fields present")
                else:
                    self.log_test("Production Jobs Enriched Fields", False, f"Missing: {missing_fields}")
            else:
                self.log_test("Production Jobs Enriched Fields", True, "Empty list (no jobs to test)")
                
        except Exception as e:
            self.log_test("Production Jobs Enriched Fields", False, f"JSON parse error: {e}")

    def test_smart_import_flow(self) -> None:
        """Test Smart Import flow end-to-end"""
        print("\n📤 Testing Smart Import Flow...")
        
        # Create a simple CSV content for testing
        csv_content = """po_number,customer_name,vendor_name,product_name,qty
TEST-PO-001,Test Buyer,Test Vendor,Test Product,100"""
        
        # Step 1: Upload
        try:
            files = {'file': ('test_po.csv', csv_content, 'text/csv')}
            data = {'data_type': 'production_po'}
            
            response = requests.post(
                f"{self.base_url}/api/smart-import/upload",
                files=files,
                data=data,
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=30
            )
            
            if response.status_code == 200:
                upload_data = response.json()
                session_id = upload_data.get('session_id')
                
                if session_id:
                    self.log_test("Smart Import - Upload", True, f"Session ID: {session_id}")
                    
                    # Step 2: Analyze
                    analyze_payload = {
                        'session_id': session_id,
                        'data_type': 'production_po'
                    }
                    
                    analyze_response = requests.post(
                        f"{self.base_url}/api/smart-import/analyze",
                        json=analyze_payload,
                        headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
                        timeout=30
                    )
                    
                    if analyze_response.status_code == 200:
                        self.log_test("Smart Import - Analyze", True, "Analysis completed")
                        
                        # Step 3: Preview (simplified)
                        preview_payload = {
                            'session_id': session_id,
                            'mapping': {
                                'po_number': 'po_number',
                                'customer_name': 'customer_name',
                                'vendor_name': 'vendor_name',
                                'product_name': 'product_name',
                                'qty': 'qty'
                            }
                        }
                        
                        preview_response = requests.post(
                            f"{self.base_url}/api/smart-import/preview",
                            json=preview_payload,
                            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
                            timeout=30
                        )
                        
                        if preview_response.status_code == 200:
                            self.log_test("Smart Import - Preview", True, "Preview generated")
                        else:
                            self.log_test("Smart Import - Preview", False, f"Status {preview_response.status_code}")
                    else:
                        self.log_test("Smart Import - Analyze", False, f"Status {analyze_response.status_code}")
                else:
                    self.log_test("Smart Import - Upload", False, "No session_id in response")
            else:
                self.log_test("Smart Import - Upload", False, f"Status {response.status_code}")
                
        except Exception as e:
            self.log_test("Smart Import Flow", False, f"Exception: {e}")

    def test_pdf_export(self) -> None:
        """Test PDF export functionality"""
        print("\n📄 Testing PDF Export...")
        
        # Test production-po PDF export
        params = {'type': 'production-po', 'id': 'test-id'}
        success, response, error = self.make_request('GET', '/api/pdf-export', params=params)
        
        if success:
            if response.status_code == 200:
                # Check if response is PDF
                content_type = response.headers.get('content-type', '')
                if 'application/pdf' in content_type or response.content.startswith(b'%PDF'):
                    self.log_test("PDF Export - production-po", True, "PDF generated successfully")
                else:
                    self.log_test("PDF Export - production-po", False, f"Not a PDF: {content_type}")
            elif response.status_code == 404:
                self.log_test("PDF Export - production-po", True, "404 expected for non-existent ID")
            else:
                self.log_test("PDF Export - production-po", False, f"Status {response.status_code}")
        else:
            self.log_test("PDF Export - production-po", False, f"Request failed: {error}")
        
        # Test report PDF export
        params = {'type': 'report-production'}
        success, response, error = self.make_request('GET', '/api/pdf-export', params=params)
        
        if success:
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'application/pdf' in content_type or response.content.startswith(b'%PDF'):
                    self.log_test("PDF Export - report-production", True, "Report PDF generated")
                else:
                    self.log_test("PDF Export - report-production", False, f"Not a PDF: {content_type}")
            else:
                self.log_test("PDF Export - report-production", False, f"Status {response.status_code}")
        else:
            self.log_test("PDF Export - report-production", False, f"Request failed: {error}")

    def run_all_tests(self) -> Dict:
        """Run all Phase 10A tests"""
        print("🚀 Starting Phase 10A Backend Pagination Tests")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📅 Test Time: {datetime.now().isoformat()}")
        
        # Authentication
        if not self.test_login():
            print("❌ Authentication failed - stopping tests")
            return self.get_summary()
        
        # Core pagination tests
        self.test_backward_compatibility()
        self.test_paginated_envelope()
        self.test_per_page_cap()
        
        # Filter and sort tests
        self.test_filters_preserved()
        self.test_sort_params()
        
        # Legacy parameter tests
        self.test_legacy_limit_param()
        self.test_buyers_legacy_pagination()
        
        # Data integrity tests
        self.test_core_crud_operations()
        self.test_n1_regression_guard()
        self.test_production_jobs_enriched_fields()
        
        # Integration tests
        self.test_smart_import_flow()
        self.test_pdf_export()
        
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
            "summary": f"Phase 10A Backend Testing: {self.tests_passed}/{self.tests_run} tests passed ({success_rate:.1f}%)"
        }

def main():
    """Main test execution"""
    tester = Phase10APaginationTester()
    
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