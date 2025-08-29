#!/usr/bin/env python3
"""
Quick local test to verify basic functionality
Run this with: python test_local.py
"""

import requests
import json
import sys

def test_local_setup():
    """Test if services are running locally"""
    
    BASE_URL = "http://localhost:8000"
    
    print("🔍 Testing Local Setup...")
    print("-" * 40)
    
    # 1. Check if backend is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Backend is running")
            health_data = response.json()
            print(f"   Status: {health_data.get('status')}")
            
            # Check Ollama connection
            ollama = health_data.get('services', {}).get('ollama', {})
            if ollama.get('healthy'):
                print("✅ Ollama connection successful")
                print(f"   Model available: {ollama.get('model_available')}")
            else:
                print("❌ Ollama connection failed")
                print("   Make sure Ollama is running: ollama serve")
        else:
            print(f"⚠️  Backend returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend")
        print("   Run: uvicorn app:app --reload")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    print()
    
    # 2. Test basic chat
    print("💬 Testing Chat Endpoint...")
    print("-" * 40)
    
    try:
        payload = {
            "message": "Respond with exactly: Hello, HIPAA-compliant world!",
            "temperature": 0.1
        }
        
        response = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            reply = data.get("reply", "")
            print("✅ Chat endpoint working")
            print(f"   Response: {reply[:100]}...")
        else:
            print(f"❌ Chat failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Chat error: {e}")
    
    print()
    
    # 3. Test PHI redaction
    print("🔒 Testing PHI Redaction...")
    print("-" * 40)
    
    try:
        # Import the redaction function
        sys.path.insert(0, '.')
        from tools.web_search import redact_phi
        
        test_text = "Patient John Doe (SSN: 123-45-6789) visited on 01/15/2024"
        redacted, items = redact_phi(test_text)
        
        if "REDACTED" in redacted and len(items) > 0:
            print("✅ PHI redaction working")
            print(f"   Original: {test_text}")
            print(f"   Redacted: {redacted}")
            print(f"   Items redacted: {len(items)}")
        else:
            print("⚠️  PHI redaction may not be working properly")
            
    except ImportError:
        print("⚠️  Could not import redaction module")
    except Exception as e:
        print(f"❌ Redaction error: {e}")
    
    print()
    print("=" * 40)
    print("Local testing complete!")
    print("=" * 40)
    
    return True

if __name__ == "__main__":
    test_local_setup()