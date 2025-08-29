# HIPAA-Compliant OSS LLM Agent

A secure, HIPAA-compliant implementation of an open-source LLM agent using Ollama and FastAPI, designed for deployment on Render's BAA-covered infrastructure.

## 🔒 Security & Compliance

- **PHI Protection**: All Protected Health Information stays within the compliant boundary
- **Private Networking**: Services communicate only via internal network
- **Encrypted Storage**: Model and data storage uses encrypted volumes
- **Audit Logging**: Comprehensive logging without PHI exposure
- **Tool Safety**: External tools automatically redact PHI

## 🏗️ Architecture

```
[Client] → [agent-backend] → [oss-llm (Ollama)]
              ↓
         [Tools: web_search, file_search, browser_action]
```

Both services run as private Render services with no public ingress to the LLM.

## 🚀 Quick Start

### Prerequisites

- Render account with HIPAA BAA signed
- Docker installed locally (for testing)
- Python 3.11+

### Local Development

1. **Clone and setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your configuration
```

2. **Run Ollama locally:**
```bash
# Pull the model
ollama pull llama3.1:8b-instruct

# Start Ollama server
ollama serve
```

3. **Start the backend:**
```bash
# For development
uvicorn app:app --reload --port 8000

# For production
uvicorn app:app --host 0.0.0.0 --port 8000
```

4. **Access the UI:**
Open http://localhost:8000 in your browser

### Render Deployment

1. **Connect your repository to Render**

2. **Create services using render.yaml:**
```bash
# Deploy using Render Blueprint
# This creates both oss-llm and agent-backend services
```

3. **Configure environment variables:**
- Set `SESSION_SECRET` to a strong random value
- Adjust `OLLAMA_MODEL` if using a different model
- Configure tool settings as needed

4. **Verify deployment:**
- Check health endpoint: `https://your-backend.onrender.com/health`
- Services should show as "Healthy" in Render dashboard

## 📁 Project Structure

```
.
├── Dockerfile           # Ollama service container
├── app.py              # FastAPI backend application
├── providers/
│   └── ollama.py       # Ollama integration
├── tools/
│   ├── web_search.py   # External search with PHI protection
│   ├── file_search.py  # Internal document search
│   └── browser_action.py # Browser automation
├── requirements.txt    # Python dependencies
├── render.yaml        # Render deployment blueprint
└── .env.example       # Environment configuration template
```

## 🛠️ Configuration

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_URL` | Internal Ollama service URL | `http://oss-llm:11434/api/chat` |
| `OLLAMA_MODEL` | LLM model to use | `llama3.1:8b-instruct` |
| `OLLAMA_TIMEOUT` | Request timeout (seconds) | `600` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `MASK_PHI_IN_LOGS` | Enable PHI masking | `true` |

### Available Models

- `llama3.1:8b-instruct` - Recommended, good balance
- `qwen2.5:7b-instruct` - Alternative, faster
- `mixtral:8x7b-instruct` - Larger, more capable (requires more resources)

## 🔧 Tools

### Web Search
- Automatically redacts PHI before external API calls
- Returns cited sources
- Configurable search providers

### File Search
- Internal document indexing
- Safe for PHI storage
- Vector similarity search

### Browser Action
- Requires user confirmation for sensitive actions
- Supports common automation patterns
- Screenshot capture capability

## 📊 Monitoring

### Health Check
```bash
curl https://your-backend.onrender.com/health
```

### Metrics
- Available at `/metrics` (Prometheus format)
- No PHI in metrics
- Tracks request counts, latencies, errors

### Audit Logs
- Stored in `/var/log/agent/audit.log`
- Contains metadata only, no PHI
- Includes user actions, tool usage, access patterns

## 🔐 Security Best Practices

1. **Never expose the Ollama service publicly**
2. **Use strong SESSION_SECRET values**
3. **Regularly rotate credentials**
4. **Monitor audit logs for suspicious activity**
5. **Keep services and dependencies updated**
6. **Test PHI redaction regularly**

## 🧪 Testing

### Unit Tests
```bash
pytest tests/
```

### PHI Redaction Test
```bash
python -m tools.web_search
# Test with: "Find info about John Doe at 123 Main St"
# Should redact name and address
```

### Integration Test
```bash
# Start services locally
docker-compose up

# Run integration tests
pytest tests/integration/
```

## 📈 Scaling

### Horizontal Scaling
- Backend can scale to multiple instances
- Ollama should remain single instance for model consistency
- Use Redis for shared session management

### Vertical Scaling
- Upgrade Render plan for more CPU/memory
- Increase disk size for larger models
- Consider GPU instances for better performance

## 🚨 Troubleshooting

### Ollama Connection Issues
- Verify private network DNS: `nslookup oss-llm`
- Check Ollama health: `curl http://oss-llm:11434/api/tags`
- Review Ollama logs in Render dashboard

### High Latency
- Check model size vs available memory
- Consider smaller model or quantization
- Review OLLAMA_NUM_PARALLEL setting

### PHI Leakage Concerns
- Review audit logs
- Check LOG_LEVEL is not DEBUG
- Verify MASK_PHI_IN_LOGS is true
- Test redaction patterns

## 📝 License

This implementation is provided as-is for HIPAA-compliant deployments. Ensure you have appropriate BAAs with all service providers.

## 🤝 Support

For issues or questions:
1. Check Render status page
2. Review audit logs
3. Contact your compliance officer for PHI-related concerns

---

**Important**: This system handles Protected Health Information. Ensure all staff are trained on HIPAA requirements and your organization's privacy policies.