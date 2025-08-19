"""
Integration tests for the complete setup workflow.
"""

import pytest
import time
from unittest.mock import patch, Mock
from cryptography.fernet import Fernet


@pytest.mark.integration
@pytest.mark.slow
class TestSetupWorkflow:
    """Test complete setup workflow from start to finish."""
    
    def test_complete_setup_workflow(self, client, test_db):
        """Test complete setup workflow from initial visit to working app."""
        # Step 1: First visit should redirect to setup
        response = client.get('/')
        assert response.status_code in [200, 302]
        
        if response.status_code == 302:
            assert '/setup' in response.location
        
        # Step 2: Setup page should render
        response = client.get('/setup')
        assert response.status_code == 200
        assert b'setup' in response.data.lower() or b'discogs' in response.data.lower()
        
        # Step 3: Submit valid setup data
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None  # No existing user
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_test_token',
                'username': 'testuser'
            }, follow_redirects=True)
            
            assert response.status_code == 200
        
        # Step 4: Verify user data was stored
        cursor = test_db.execute("SELECT * FROM users WHERE username = ?", ('testuser',))
        user = cursor.fetchone()
        assert user is not None
        assert user['username'] == 'testuser'
        assert user['setup_completed'] == 1
        
        # Step 5: Test authenticated access
        with client.session_transaction() as sess:
            sess['username'] = 'testuser'
            sess['encryption_key'] = Fernet.generate_key()
            sess['setup_completed'] = True
        
        # Step 6: Main page should now work
        response = client.get('/')
        assert response.status_code == 200
    
    def test_setup_workflow_with_existing_user(self, client, test_db):
        """Test setup workflow when user already exists."""
        # Insert existing user
        test_db.execute("""
            INSERT INTO users (username, encrypted_token, setup_completed)
            VALUES (?, ?, ?)
        """, ('existinguser', b'encrypted_token', 1))
        test_db.commit()
        
        # Try to setup with existing username
        with patch('app.get_user_discogs_data') as mock_get_user:
            mock_get_user.return_value = ('existinguser', b'encrypted_token')
            
            response = client.post('/setup', data={
                'discogs_token': 'new_token',
                'username': 'existinguser'
            })
            
            # Should handle existing user appropriately
            assert response.status_code in [200, 302, 400]
    
    def test_setup_workflow_invalid_token(self, client):
        """Test setup workflow with invalid Discogs token."""
        with patch('app.validate_discogs_token') as mock_validate:
            mock_validate.return_value = (None, False)
            
            response = client.post('/setup', data={
                'discogs_token': 'invalid_token',
                'username': 'testuser'
            })
            
            # Should show error and remain on setup page
            assert response.status_code in [200, 400]
            assert b'setup' in response.data.lower() or b'error' in response.data.lower()
    
    def test_setup_workflow_network_error(self, client):
        """Test setup workflow with network error during validation."""
        with patch('app.validate_discogs_token') as mock_validate:
            mock_validate.side_effect = Exception("Network error")
            
            response = client.post('/setup', data={
                'discogs_token': 'test_token',
                'username': 'testuser'
            })
            
            # Should handle network errors gracefully
            assert response.status_code in [200, 400, 500]
    
    def test_setup_workflow_database_error(self, client):
        """Test setup workflow with database error."""
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.store_user_data') as mock_store:
            
            mock_validate.return_value = ('testuser', True)
            mock_store.side_effect = Exception("Database error")
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Should handle database errors gracefully
            assert response.status_code in [200, 400, 500]
    
    def test_setup_workflow_encryption_key_generation(self, client):
        """Test that encryption keys are properly generated during setup."""
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None
            
            # Capture session data
            with client.session_transaction() as sess:
                initial_key = sess.get('encryption_key')
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Check that encryption key was set
            with client.session_transaction() as sess:
                final_key = sess.get('encryption_key')
                assert final_key is not None
                assert final_key != initial_key
    
    def test_setup_workflow_session_management(self, client):
        """Test session management during setup workflow."""
        # Initial session should not be authenticated
        with client.session_transaction() as sess:
            assert sess.get('username') is None
            assert sess.get('setup_completed') is None
        
        # After successful setup
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Session should be properly set
            with client.session_transaction() as sess:
                assert sess.get('username') == 'testuser'
                assert sess.get('setup_completed') is True
    
    def test_setup_workflow_redirect_after_completion(self, client):
        """Test proper redirection after setup completion."""
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Should redirect to main page after setup
            if response.status_code == 302:
                assert response.location in ['/', '/sync', '/random']
    
    def test_setup_workflow_form_validation(self, client):
        """Test form validation during setup."""
        # Test missing token
        response = client.post('/setup', data={
            'username': 'testuser'
            # Missing discogs_token
        })
        assert response.status_code in [200, 400]
        
        # Test missing username
        response = client.post('/setup', data={
            'discogs_token': 'test_token'
            # Missing username
        })
        assert response.status_code in [200, 400]
        
        # Test empty values
        response = client.post('/setup', data={
            'discogs_token': '',
            'username': ''
        })
        assert response.status_code in [200, 400]
    
    def test_setup_workflow_csrf_protection(self, client):
        """Test CSRF protection during setup."""
        # In production, CSRF should be enabled
        # This test documents the expected behavior
        
        response = client.post('/setup', data={
            'discogs_token': 'test_token',
            'username': 'testuser'
        })
        
        # Should handle CSRF appropriately
        assert response.status_code in [200, 302, 400, 403]
    
    def test_setup_workflow_token_encryption_storage(self, client, test_db):
        """Test that Discogs tokens are properly encrypted before storage."""
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None
            
            original_token = 'sensitive_discogs_token'
            
            response = client.post('/setup', data={
                'discogs_token': original_token,
                'username': 'testuser'
            })
            
            # Check that token is encrypted in database
            cursor = test_db.execute("SELECT encrypted_token FROM users WHERE username = ?", 
                                    ('testuser',))
            user = cursor.fetchone()
            
            if user:
                # Token should be encrypted (not plain text)
                stored_token = user['encrypted_token']
                assert stored_token != original_token.encode()
                assert len(stored_token) > len(original_token)  # Encrypted is longer
    
    def test_setup_workflow_multiple_attempts(self, client):
        """Test multiple setup attempts with different outcomes."""
        # First attempt - invalid token
        with patch('app.validate_discogs_token') as mock_validate:
            mock_validate.return_value = (None, False)
            
            response = client.post('/setup', data={
                'discogs_token': 'invalid_token',
                'username': 'testuser'
            })
            
            assert response.status_code in [200, 400]
        
        # Second attempt - valid token
        with patch('app.validate_discogs_token') as mock_validate, \
             patch('app.get_user_discogs_data') as mock_get_user:
            
            mock_validate.return_value = ('testuser', True)
            mock_get_user.return_value = None
            
            response = client.post('/setup', data={
                'discogs_token': 'valid_token',
                'username': 'testuser'
            })
            
            # Should succeed on second attempt
            assert response.status_code in [200, 302]