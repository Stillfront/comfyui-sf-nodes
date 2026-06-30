import time
import requests
from .utils import BaseRequest
import PIL.Image
import io
import base64


class WaveSpeedClient:
    """
    WaveSpeed AI API Client

    This class handles the core communication with the WaveSpeed AI API.
    """

    BASE_URL = "https://api.wavespeed.ai"

    def __init__(self, api_key):
        """
        Initialize WaveSpeed AI API client

        Args:
            api_key (str): WaveSpeed AI API key
        """
        self.api_key = api_key
        self.once_timeout = 1800  # Default timeout is 1800 seconds (30 minutes)

        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def post(self, endpoint, payload, timeout=30):
        """
        Send POST request to WaveSpeed AI API

        Args:
            endpoint (str): API endpoint
            payload (dict): Request payload
            timeout (float, optional): Request timeout in seconds

        Returns:
            dict: API response
        """
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.post(url, headers=self.headers, json=payload, timeout=timeout)

        if response.status_code == 401:
            raise Exception("Unauthorized: Invalid API key")

        if response.status_code != 200:
            error_message = f"Error: {response.status_code}"
            try:
                error_data = response.json()
                if "message" in error_data:
                    error_message = f"Error: {error_data['message']}"
            except:
                pass
            raise Exception(error_message)

        response_data = response.json()
        if isinstance(response_data, dict) and 'code' in response_data:
            if response_data['code'] == 401:
                raise Exception("Unauthorized: Invalid API key")
            if response_data['code'] != 200:
                raise Exception(f"API Error: {response_data.get('message', 'Unknown error')}")
            return response_data.get('data', {})
        return response_data

    def get(self, endpoint, params=None, timeout=30):
        """
        Send GET request to WaveSpeed AI API

        Args:
            endpoint (str): API endpoint
            params (dict, optional): Query parameters
            timeout (float, optional): Request timeout in seconds

        Returns:
            dict: API response
        """
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=timeout)

        if response.status_code != 200:
            error_message = f"Error: {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_message = f"Error: {error_data['error']}"
            except:
                pass
            raise Exception(error_message)

        response_data = response.json()
        if isinstance(response_data, dict) and 'code' in response_data:
            if response_data['code'] != 200:
                raise Exception(f"API Error: {response_data.get('message', 'Unknown error')}")
            return response_data.get('data', {})
        return response_data

    def check_task_status(self, request_id):
        """
        Check the status of a task

        Args:
            request_id (str): Task ID

        Returns:
            dict: Task status information, including status, progress, output, etc.
        """
        if not request_id:
            raise Exception("No valid task ID provided")
        return self.get(f"/api/v2/predictions/{request_id}/result")

    def wait_for_task(self, request_id, polling_interval=5, timeout=None):
        """
        Wait for task completion and return the result

        Args:
            request_id (str, optional): Task ID.
            polling_interval (int): Polling interval in seconds.
            timeout (int): Maximum time to wait for task completion in seconds.

        Returns:
            dict: Task result.

        Raises:
            Exception: If the task fails or times out.
        """
        if not timeout:
            timeout = self.once_timeout

        if not request_id:
            raise Exception("No valid task ID provided")

        start_time = time.time()
        while time.time() - start_time < timeout:
            task_status = self.check_task_status(request_id)
            status = task_status.get("status")

            if status == "completed":
                return task_status
            elif status == "failed":
                error_message = task_status.get("error", "Task failed")
                raise Exception(f"Task failed: {error_message}")

            time.sleep(polling_interval)

        raise Exception("Task timed out")

    def send_request(self, request: BaseRequest, wait_for_completion=True, polling_interval=5, timeout=None):
        """
        Sends an API request using a request object.

        Args:
            request (BaseRequest): The request object containing payload and endpoint logic.
            wait_for_completion (bool, optional): Whether to wait for task completion.
            polling_interval (int): Polling interval in seconds.
            timeout (int): Maximum time to wait for task completion in seconds.

        Returns:
            dict: API response or task result.
        """
        payload = request.build_payload()
        payload["enable_base64_output"] = False
        if "seed" in payload:
            payload["seed"] = payload["seed"] % 9999999999 if payload["seed"] != -1 else -1
        response = self.post(request.get_api_path(), payload)
        request_id = response.get("id")
        if not request_id:
            raise Exception("No request ID in response")

        if not wait_for_completion:
            return {"request_id": request_id, "status": "processing"}

        task_result = self.wait_for_task(request_id, polling_interval=polling_interval, timeout=timeout)
        return task_result

    def upload_file(self, image: PIL.Image.Image, max_retries=3):
        """
        Upload a file to WaveSpeed AI API with retry logic for SSL issues

        Args:
            image (PIL.Image.Image): Image to be uploaded
            max_retries (int): Maximum number of retry attempts

        Returns:
            str: Download URL of the uploaded file
        """
        url = f"{self.BASE_URL}/api/v2/media/upload/binary"
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        buffered.seek(0)
        
        headers = {'Authorization': f'Bearer {self.api_key}'}
        files = {'file': ('image.png', buffered, 'image/png')}
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Reset buffer position for retry attempts
                buffered.seek(0)
                
                # Configure session with SSL settings
                session = requests.Session()
                # Add SSL adapter configuration
                session.verify = True
                
                response = session.post(
                    url, 
                    headers=headers, 
                    files={'file': ('image.png', buffered, 'image/png')},
                    timeout=30
                )

                if response.status_code != 200:
                    raise Exception(f"Upload failed with status {response.status_code}: {response.text}")

                response_data = response.json()
                if isinstance(response_data, dict) and 'code' in response_data:
                    if response_data['code'] != 200:
                        raise Exception(f"API Error: {response_data.get('message', 'Unknown error')}")
                    return response_data.get('data', {})["download_url"]
                    
                # If we get here, no proper response structure
                raise Exception("No download URL in response")
                
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                last_exception = e
                print(f"Upload attempt {attempt + 1} failed with SSL/Connection error: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Progressive backoff: 2, 4, 6 seconds
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    break
            except Exception as e:
                # For non-SSL errors, don't retry
                raise e
            finally:
                if 'session' in locals():
                    session.close()
        
        # If we get here, all retries failed
        raise Exception(f"Upload failed after {max_retries} attempts. Last error: {str(last_exception)}")


    def upload_file_with_type(self, file_path: str, file_type: str, max_retries=3):
        """
        Upload a file to WaveSpeed AI API with retry logic for SSL issues

        Args:
            file_path (str): Path to the file to be uploaded
            file_type (str): MIME type of the file
            max_retries (int): Maximum number of retry attempts

        Returns:
            str: Download URL of the uploaded file
        """
        url = f"{self.BASE_URL}/api/v2/media/upload/binary"
        
        # Determine file name based on type
        file_name = ""
        if "video" in file_type:
           file_name = "video.mp4"
        elif "image" in file_type:
            file_name = "image.png"
        elif "audio" in file_type:
            file_name = "audio.mp3"
        else:
            raise Exception("Invalid file type")
            
        headers = {'Authorization': f'Bearer {self.api_key}'}
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # Configure session with SSL settings
                session = requests.Session()
                session.verify = True
                
                with open(file_path, "rb") as file:
                    files = {'file': (file_name, file, file_type)}
                    response = session.post(
                        url, 
                        headers=headers, 
                        files=files,
                        timeout=60  # Longer timeout for file uploads
                    )

                if response.status_code != 200:
                    raise Exception(f"Upload failed with status {response.status_code}: {response.text}")

                response_data = response.json()
                if isinstance(response_data, dict) and 'code' in response_data:
                    if response_data['code'] != 200:
                        raise Exception(f"API Error: {response_data.get('message', 'Unknown error')}")
                    return response_data.get('data', {})["download_url"]
                    
                # If we get here, no proper response structure
                raise Exception("No download URL in response")
                
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                last_exception = e
                print(f"Upload attempt {attempt + 1} failed with SSL/Connection error: {str(e)}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Progressive backoff: 2, 4, 6 seconds
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    break
            except Exception as e:
                # For non-SSL errors, don't retry
                raise e
            finally:
                if 'session' in locals():
                    session.close()
        
        # If we get here, all retries failed
        raise Exception(f"Upload failed after {max_retries} attempts. Last error: {str(last_exception)}")