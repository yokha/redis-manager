# **Packaging and Release**

Redis Manager's packaging and release process is manually managed using Makefile targets. This approach ensures precise control over build artifacts, testing, and deployment to **Test PyPI** or **PyPI**.

---

## **Makefile Targets and Commands**

### **1. Clean Up Build Artifacts**
- Cleans up build directories and virtual environments.
  ```bash
  make clean-pkg-venv
  ```

### **2. Package the Project**
- Builds the source distribution (`sdist`) and wheel distribution (`bdist_wheel`).
  ```bash
  make package
  ```

### **3. Release to Test PyPI**
- Uploads the package to **Test PyPI** for testing purposes.
  ```bash
  export TWINE_USERNAME="__token__"
  export TWINE_PASSWORD="your-test-pypi-api-token"

  make Release-pypi-test
  ```

### **4. Verify Release to Test PyPI**
- Installs the package from **Test PyPI** in a fresh environment to verify its functionality.
  ```bash
  make verify-test-release
  ```

### **5. Release to PyPI**
- Publishes the package to the official **PyPI** repository.
  ```bash
  export TWINE_USERNAME="__token__"
  export TWINE_PASSWORD="your-prod-pypi-api-token"

  make Release-pypi
  ```

### **6. Verify Release to PyPI**
- Similar to Test PyPI verification, confirms the published package works correctly when installed from **PyPI**.
  ```bash
  make verify-test-release
  ```

### **7. Tag a Release Version**
- Tags the current state of the repository with a release version for tracking purposes.
  ```bash
  make tag-release
  ```

---

## **Additional Notes**
- Ensure your `TWINE_USERNAME` and `TWINE_PASSWORD` environment variables are set before running the release commands.
- Use the verification steps after every release to ensure the package works as expected.
- These manual steps provide fine-grained control and oversight during the packaging and release process.

[🔙 Return to README](../README.md)
