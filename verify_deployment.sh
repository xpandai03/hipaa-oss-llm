#!/bin/bash

# HIPAA-Compliant Deployment Verification Script
# Run this on your Render backend shell to verify private network connectivity

echo "=========================================="
echo "DEPLOYMENT VERIFICATION SCRIPT"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check environment variables
echo "1. Checking Environment Variables..."
echo "-----------------------------------"

if [ -z "$OLLAMA_URL" ]; then
    echo -e "${RED}❌ OLLAMA_URL not set${NC}"
else
    echo -e "${GREEN}✅ OLLAMA_URL = $OLLAMA_URL${NC}"
fi

if [ -z "$OLLAMA_MODEL" ]; then
    echo -e "${RED}❌ OLLAMA_MODEL not set${NC}"
else
    echo -e "${GREEN}✅ OLLAMA_MODEL = $OLLAMA_MODEL${NC}"
fi

echo ""

# Test 2: DNS resolution for oss-llm service
echo "2. Testing DNS Resolution..."
echo "----------------------------"

if nslookup oss-llm > /dev/null 2>&1; then
    echo -e "${GREEN}✅ DNS resolution for 'oss-llm' successful${NC}"
    nslookup oss-llm | grep -A1 "Name:"
else
    echo -e "${RED}❌ Cannot resolve 'oss-llm' - check service name${NC}"
fi

echo ""

# Test 3: Network connectivity to Ollama
echo "3. Testing Network Connectivity..."
echo "----------------------------------"

OLLAMA_HOST="oss-llm:11434"
if nc -zv oss-llm 11434 2>&1 | grep -q "succeeded"; then
    echo -e "${GREEN}✅ Can connect to Ollama on port 11434${NC}"
else
    echo -e "${RED}❌ Cannot connect to Ollama on port 11434${NC}"
fi

echo ""

# Test 4: Ollama API health check
echo "4. Testing Ollama API..."
echo "------------------------"

OLLAMA_TAGS_URL="http://oss-llm:11434/api/tags"
echo "Checking $OLLAMA_TAGS_URL"

TAGS_RESPONSE=$(curl -s -w "\n%{http_code}" $OLLAMA_TAGS_URL 2>/dev/null)
HTTP_CODE=$(echo "$TAGS_RESPONSE" | tail -n1)
BODY=$(echo "$TAGS_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Ollama API responding (HTTP $HTTP_CODE)${NC}"
    
    # Check if model is available
    if echo "$BODY" | grep -q "llama3.1:8b-instruct"; then
        echo -e "${GREEN}✅ Model 'llama3.1:8b-instruct' is available${NC}"
    else
        echo -e "${YELLOW}⚠️  Model 'llama3.1:8b-instruct' not found in model list${NC}"
        echo "Available models:"
        echo "$BODY" | python3 -m json.tool | grep "name" || echo "$BODY"
    fi
else
    echo -e "${RED}❌ Ollama API error (HTTP $HTTP_CODE)${NC}"
fi

echo ""

# Test 5: Test chat endpoint
echo "5. Testing Ollama Chat Endpoint..."
echo "----------------------------------"

CHAT_URL="http://oss-llm:11434/api/chat"
CHAT_PAYLOAD='{"model":"llama3.1:8b-instruct","messages":[{"role":"user","content":"Say hello"}],"stream":false}'

echo "Sending test chat request..."
CHAT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d "$CHAT_PAYLOAD" \
    --max-time 30 \
    $CHAT_URL 2>/dev/null)

CHAT_HTTP_CODE=$(echo "$CHAT_RESPONSE" | tail -n1)
CHAT_BODY=$(echo "$CHAT_RESPONSE" | head -n-1)

if [ "$CHAT_HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Chat endpoint working (HTTP $CHAT_HTTP_CODE)${NC}"
    
    # Extract and display the response
    if echo "$CHAT_BODY" | grep -q "content"; then
        CONTENT=$(echo "$CHAT_BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('message', {}).get('content', 'No content')[:100])" 2>/dev/null)
        echo "Response preview: $CONTENT..."
    fi
else
    echo -e "${RED}❌ Chat endpoint error (HTTP $CHAT_HTTP_CODE)${NC}"
    echo "Error: $CHAT_BODY"
fi

echo ""

# Test 6: Check for PHI in logs
echo "6. Checking for PHI in Recent Logs..."
echo "-------------------------------------"

# This checks if common PHI patterns appear in logs
# In production, this should be more comprehensive

LOG_CHECK_PATTERNS=(
    "[0-9]{3}-[0-9]{2}-[0-9]{4}"  # SSN pattern
    "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"  # Email
    "[0-9]{3}[-.]?[0-9]{3}[-.]?[0-9]{4}"  # Phone
)

echo "Checking last 100 lines of application logs for PHI patterns..."
PHI_FOUND=false

# Note: Adjust log location based on your Render setup
if [ -f "/var/log/app.log" ]; then
    for pattern in "${LOG_CHECK_PATTERNS[@]}"; do
        if tail -n 100 /var/log/app.log | grep -qE "$pattern"; then
            echo -e "${RED}❌ Potential PHI pattern found in logs${NC}"
            PHI_FOUND=true
            break
        fi
    done
    
    if [ "$PHI_FOUND" = false ]; then
        echo -e "${GREEN}✅ No obvious PHI patterns found in recent logs${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Log file not found at expected location${NC}"
fi

echo ""

# Test 7: Memory and resource check
echo "7. Resource Usage..."
echo "-------------------"

echo "Memory usage:"
free -h | grep "Mem:" | awk '{print "  Total: " $2 "  Used: " $3 "  Free: " $4}'

echo ""
echo "Disk usage:"
df -h / | tail -n1 | awk '{print "  Total: " $2 "  Used: " $3 "  Available: " $4 "  Use%: " $5}'

echo ""

# Summary
echo "=========================================="
echo "VERIFICATION COMPLETE"
echo "=========================================="

# Count successes
SUCCESS_COUNT=0
TOTAL_TESTS=7

if [ ! -z "$OLLAMA_URL" ]; then ((SUCCESS_COUNT++)); fi
if nslookup oss-llm > /dev/null 2>&1; then ((SUCCESS_COUNT++)); fi
if nc -zv oss-llm 11434 2>&1 | grep -q "succeeded"; then ((SUCCESS_COUNT++)); fi
if [ "$HTTP_CODE" = "200" ]; then ((SUCCESS_COUNT++)); fi
if [ "$CHAT_HTTP_CODE" = "200" ]; then ((SUCCESS_COUNT++)); fi
if [ "$PHI_FOUND" = false ]; then ((SUCCESS_COUNT++)); fi

echo ""
echo "Tests Passed: $SUCCESS_COUNT / $TOTAL_TESTS"

if [ $SUCCESS_COUNT -eq $TOTAL_TESTS ]; then
    echo -e "${GREEN}✅ All tests passed! Deployment verified.${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some tests failed. Please review the output above.${NC}"
    exit 1
fi