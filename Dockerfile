FROM --platform=linux/amd64 python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages (ECS Streamlit app only; agent runs on AgentCore)
RUN pip install streamlit boto3 langchain_aws langchain-openai "openai>=2.41.0" aws-bedrock-token-generator requests

RUN mkdir -p /root/.streamlit
COPY config.toml /root/.streamlit/

COPY . .

RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "streamlit", "run", "application/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
