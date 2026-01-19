# Use Python 3.11 to fix those "End of Life" warnings
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# COPY EVERYTHING from GitHub into the server
# (This ensures app.py, requirements.txt, AND your logo are all copied)
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Open the port
EXPOSE 8501

# Run the app
CMD streamlit run app.py --server.port=8501 --server.address=0.0.0.0
