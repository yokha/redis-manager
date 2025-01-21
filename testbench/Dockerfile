# Use Python slim image
FROM python:3.12-slim

# Set working directory to the app
WORKDIR /usr/src

# Copy the testbench app
COPY testbench/app /usr/src/app

# Copy the library source code
COPY src /usr/src/src

# Copy the pyproject.toml for the library
COPY pyproject.toml /usr/src/pyproject.toml

# Install the library
RUN pip install /usr/src

# Install requirements for the testbench
COPY testbench/app/requirements.txt requirements.txt

RUN pip install --upgrade pip && pip install -r requirements.txt

# Set PYTHONPATH for module discovery
ENV ENV PYTHONPATH=/usr/src

# Expose FastAPI server port
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
