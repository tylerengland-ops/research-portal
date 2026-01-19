# 1. Use a lightweight Python version
FROM python:3.9-slim

# 2. Set the working directory inside the server
WORKDIR /app

# 3. Copy your specific files into the server
COPY requirements.txt ./
COPY app.py ./
COPY .streamlit ./.streamlit
# Copy any other folders you need, e.g., images:
# COPY images ./images 

# 4. Install your libraries
RUN pip install --no-cache-dir -r requirements.txt

# 5. Open the port Railway expects
EXPOSE 8501

# 6. The Command to run the app
# Note: We use $PORT provided by Railway
CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
