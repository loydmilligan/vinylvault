"""
Docker deployment tests for VinylVault.
Tests Docker build process, health checks, and volume mounting.
"""

import pytest
import docker
import time
import requests
import subprocess
import os
from pathlib import Path


@pytest.mark.docker
@pytest.mark.deployment
class TestDockerDeployment:
    """Test Docker deployment functionality."""
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and is readable."""
        dockerfile_path = Path(__file__).parent.parent.parent / "Dockerfile"
        assert dockerfile_path.exists(), "Dockerfile not found"
        
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            assert "FROM python:" in content, "Dockerfile should use Python base image"
            assert "COPY requirements.txt" in content, "Should copy requirements.txt"
            assert "RUN pip install" in content, "Should install dependencies"
            assert "EXPOSE 5000" in content, "Should expose port 5000"
    
    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists and is valid."""
        compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"
        
        with open(compose_path, 'r') as f:
            content = f.read()
            assert "vinylvault:" in content, "Should define vinylvault service"
            assert "ports:" in content, "Should define port mapping"
            assert "volumes:" in content, "Should define volume mounts"
            assert "healthcheck:" in content, "Should define health check"
    
    @pytest.mark.slow
    def test_docker_build(self, docker_services):
        """Test Docker image build process."""
        client = docker_services
        project_root = Path(__file__).parent.parent.parent
        
        try:
            # Build the image
            image, logs = client.images.build(
                path=str(project_root),
                tag="vinylvault:test",
                rm=True,
                forcerm=True
            )
            
            # Verify image was created
            assert image is not None, "Docker image should be built successfully"
            assert "vinylvault:test" in [tag for tag in image.tags], "Image should be tagged correctly"
            
            # Check image layers
            history = image.history()
            assert len(history) > 0, "Image should have build history"
            
        except docker.errors.BuildError as e:
            pytest.fail(f"Docker build failed: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error during Docker build: {e}")
    
    @pytest.mark.slow
    def test_docker_container_startup(self, docker_services):
        """Test container startup and basic functionality."""
        client = docker_services
        project_root = Path(__file__).parent.parent.parent
        
        # Ensure image is built
        try:
            client.images.get("vinylvault:test")
        except docker.errors.ImageNotFound:
            pytest.skip("Docker image not built, run test_docker_build first")
        
        container = None
        try:
            # Create and start container
            container = client.containers.run(
                "vinylvault:test",
                ports={'5000/tcp': ('127.0.0.1', 0)},  # Random available port
                detach=True,
                remove=True,
                environment={
                    'FLASK_ENV': 'testing',
                    'PORT': '5000'
                }
            )
            
            # Wait for container to start
            time.sleep(10)
            
            # Get assigned port
            container.reload()
            port_info = container.ports.get('5000/tcp')
            assert port_info, "Port 5000 should be exposed"
            
            host_port = port_info[0]['HostPort']
            
            # Test basic connectivity
            max_retries = 30
            for i in range(max_retries):
                try:
                    response = requests.get(f"http://127.0.0.1:{host_port}/", timeout=5)
                    if response.status_code in [200, 302]:  # 302 for redirect to setup
                        break
                except requests.exceptions.RequestException:
                    if i == max_retries - 1:
                        pytest.fail("Container failed to respond after 30 attempts")
                    time.sleep(1)
            
            # Verify container is running
            container.reload()
            assert container.status == "running", "Container should be running"
            
        finally:
            if container:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
    
    @pytest.mark.slow
    def test_health_check(self, docker_services):
        """Test Docker health check functionality."""
        client = docker_services
        
        try:
            client.images.get("vinylvault:test")
        except docker.errors.ImageNotFound:
            pytest.skip("Docker image not built, run test_docker_build first")
        
        container = None
        try:
            # Start container with health check
            container = client.containers.run(
                "vinylvault:test",
                ports={'5000/tcp': ('127.0.0.1', 0)},
                detach=True,
                remove=True,
                environment={
                    'FLASK_ENV': 'testing',
                    'PORT': '5000'
                }
            )
            
            # Wait for health check to complete
            max_wait = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                container.reload()
                health = container.attrs.get('State', {}).get('Health', {})
                status = health.get('Status')
                
                if status == 'healthy':
                    break
                elif status == 'unhealthy':
                    pytest.fail("Container health check failed")
                
                time.sleep(5)
            
            # Verify final health status
            container.reload()
            health = container.attrs.get('State', {}).get('Health', {})
            assert health.get('Status') == 'healthy', "Container should be healthy"
            
        finally:
            if container:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
    
    @pytest.mark.slow
    def test_volume_persistence(self, docker_services, tmp_path):
        """Test volume mounting and data persistence."""
        client = docker_services
        
        try:
            client.images.get("vinylvault:test")
        except docker.errors.ImageNotFound:
            pytest.skip("Docker image not built, run test_docker_build first")
        
        # Create temporary directories for volumes
        cache_dir = tmp_path / "cache"
        logs_dir = tmp_path / "logs"
        cache_dir.mkdir()
        logs_dir.mkdir()
        
        container = None
        try:
            # Start container with volume mounts
            container = client.containers.run(
                "vinylvault:test",
                ports={'5000/tcp': ('127.0.0.1', 0)},
                volumes={
                    str(cache_dir): {'bind': '/app/cache', 'mode': 'rw'},
                    str(logs_dir): {'bind': '/app/logs', 'mode': 'rw'}
                },
                detach=True,
                remove=True,
                environment={
                    'FLASK_ENV': 'testing',
                    'PORT': '5000'
                }
            )
            
            # Wait for container to start and create files
            time.sleep(15)
            
            # Check that files are created in mounted volumes
            # Database should be created
            db_file = cache_dir / "vinylvault.db"
            log_file = logs_dir / "vinylvault.log"
            
            # Wait a bit more for files to be created
            max_wait = 60
            start_time = time.time()
            while time.time() - start_time < max_wait:
                if db_file.exists() or log_file.exists():
                    break
                time.sleep(2)
            
            # At least one file should exist (database gets created on first access)
            assert db_file.exists() or log_file.exists(), "Volume-mounted files should be created"
            
        finally:
            if container:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass
    
    def test_docker_compose_validation(self):
        """Test docker-compose configuration validation."""
        project_root = Path(__file__).parent.parent.parent
        compose_file = project_root / "docker-compose.yml"
        
        # Run docker-compose config to validate
        try:
            result = subprocess.run(
                ["docker-compose", "-f", str(compose_file), "config"],
                capture_output=True,
                text=True,
                cwd=project_root
            )
            
            assert result.returncode == 0, f"docker-compose config failed: {result.stderr}"
            
            # Check that config output contains expected services
            config_output = result.stdout
            assert "vinylvault:" in config_output, "vinylvault service should be in config"
            assert "ports:" in config_output, "Ports should be configured"
            assert "volumes:" in config_output, "Volumes should be configured"
            
        except FileNotFoundError:
            pytest.skip("docker-compose not available")
    
    @pytest.mark.slow
    def test_environment_variables(self, docker_services):
        """Test environment variable handling in container."""
        client = docker_services
        
        try:
            client.images.get("vinylvault:test")
        except docker.errors.ImageNotFound:
            pytest.skip("Docker image not built, run test_docker_build first")
        
        container = None
        try:
            # Test with custom environment variables
            container = client.containers.run(
                "vinylvault:test",
                environment={
                    'FLASK_ENV': 'production',
                    'PORT': '5000',
                    'CUSTOM_VAR': 'test_value'
                },
                detach=True,
                remove=True
            )
            
            # Wait for container to start
            time.sleep(5)
            
            # Check environment variables are set
            exec_result = container.exec_run("env")
            env_output = exec_result.output.decode()
            
            assert "FLASK_ENV=production" in env_output, "FLASK_ENV should be set"
            assert "PORT=5000" in env_output, "PORT should be set"
            assert "CUSTOM_VAR=test_value" in env_output, "Custom variables should be set"
            
        finally:
            if container:
                try:
                    container.stop(timeout=10)
                except Exception:
                    pass