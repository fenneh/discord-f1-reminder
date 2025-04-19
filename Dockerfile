# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# Note: .env is NOT copied here; it should be provided at runtime.
COPY main.py .

# Command to run the application when the container launches
# The script will load variables from the .env file passed at runtime
CMD ["python", "main.py"] 