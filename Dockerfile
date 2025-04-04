# Use an official Python runtime as a parent image
FROM python:3.12-slim
# Set the working directory in the container to /app
WORKDIR /app

# Add the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in depends.txt
RUN pip install -r requirements.txt

# Run main.py when the container launches
CMD ["python", "src/main.py"]
