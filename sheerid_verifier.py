import requests
import re
import json
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://batch.1key.me"

class SheerIDVerifier:
    def __init__(self, api_key: str = ""):
        self.session = requests.Session()
        self.api_key = api_key
        self.csrf_token = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/"
        }

    def verify_single(self, link_or_id, callback=None, return_extra=False):
        """
        Verify a single SheerID link or verificationId.

        Returns:
            (success: bool, verification_id: str|None, message: str)
            return_extra=True 时返回 (success, verification_id, message, bind_url)
        """
        if not link_or_id:
            return False, None, "空链接/ID"

        vid = None
        if isinstance(link_or_id, str):
            match_param = re.search(r'verificationId=([a-zA-Z0-9]+)', link_or_id)
            if match_param:
                vid = match_param.group(1)
            else:
                match_path = re.search(r'verify/([a-zA-Z0-9]+)', link_or_id)
                if match_path:
                    vid = match_path.group(1)
                elif re.match(r'^[a-zA-Z0-9]+$', link_or_id):
                    vid = link_or_id

        if not vid:
            return False, None, "未找到 verificationId"

        results = self.verify_batch([vid], callback=callback)
        res = results.get(vid)
        if not res:
            return False, vid, "未获取到验证结果"

        status = res.get("currentStep") or res.get("status")
        message = res.get("message", "")
        bind_url = res.get("bindUrl") or res.get("_bindUrl")
        if status == "success":
            if return_extra:
                return True, vid, message or "success", bind_url
            return True, vid, message or "success"
        if return_extra:
            return False, vid, message or (status or "error"), bind_url
        return False, vid, message or (status or "error")

    def verify_single_with_bind(self, link_or_id, callback=None):
        """
        验证单个链接并返回绑卡链接（若可提取）

        Returns:
            (success: bool, verification_id: str|None, message: str, bind_url: str|None)
        """
        return self.verify_single(link_or_id, callback=callback, return_extra=True)

    def _get_csrf_token(self):
        """Fetch homepage and extract CSRF token"""
        try:
            logger.info("Fetching CSRF token...")
            resp = self.session.get(BASE_URL, headers=self.headers, timeout=10)
            resp.raise_for_status()
            
            logger.debug(f"Response status: {resp.status_code}")
            logger.debug(f"Response length: {len(resp.text)} chars")
            
            # 尝试多种 CSRF token 模式
            patterns = [
                r'window\.CSRF_TOKEN\s*=\s*["\']([^"\']+)["\']',  # window.CSRF_TOKEN = "..."
                r'csrfToken["\']?\s*[:=]\s*["\']([^"\']+)["\']',  # csrfToken: "..." or csrfToken = "..."
                r'_csrf["\']?\s*[:=]\s*["\']([^"\']+)["\']',      # _csrf: "..." or _csrf = "..."
            ]
            
            for i, pattern in enumerate(patterns):
                match = re.search(pattern, resp.text, re.IGNORECASE)
                if match:
                    self.csrf_token = match.group(1)
                    self.headers["X-CSRF-Token"] = self.csrf_token
                    logger.info(f"✅ CSRF Token obtained (pattern {i+1}): {self.csrf_token[:10]}...")
                    return True
            
            # 如果都没匹配到，输出更详细的调试信息
            logger.error("❌ CSRF Token pattern not found in page.")
            logger.error(f"Page content preview (first 1000 chars):\n{resp.text[:1000]}")
            
            # 查找所有可能的 token 相关字符串
            token_hints = re.findall(r'(csrf|token|_token)[^"\']*["\']([^"\']{20,})["\']', resp.text, re.IGNORECASE)
            if token_hints:
                logger.info(f"Found potential token patterns: {token_hints[:3]}")
            
            # 尝试不使用 CSRF token 继续
            logger.warning("Attempting to proceed without CSRF token...")
            return False
            
        except Exception as e:
            logger.error(f"Failed to get CSRF token: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def verify_batch(self, verification_ids, callback=None):
        """
        Verify a batch of IDs (list of strings).
        Returns a dict {verification_id: status_result}
        """
        # 每次批次验证前都刷新 CSRF token，确保 token 有效
        logger.info("Refreshing CSRF token before batch...")
        if not self._get_csrf_token():
            logger.warning("CSRF token refresh failed, attempting with old/no token")

        results = {}
        # Max 5 IDs per batch if API key is present
        # API requires hCaptchaToken to be the API Key for bypass
        
        payload = {
            "verificationIds": verification_ids,
            "hCaptchaToken": self.api_key, 
            "useLucky": False,
            "programId": ""
        }
        
        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"

        try:
            logger.info(f"Submitting batch verification for {len(verification_ids)} IDs...")
            logger.info(f"🔑 API Key: {self.api_key[:10] if self.api_key else '❌ EMPTY'}...")
            logger.info(f"📦 Payload: verificationIds={verification_ids}, hCaptchaToken={self.api_key[:10] if self.api_key else 'NONE'}...")
            
            resp = self.session.post(
                f"{BASE_URL}/api/batch", 
                headers=headers, 
                json=payload,
                stream=True,
                timeout=30
            )
            
            # 如果返回 403/401，说明 token 还是过期了，再试一次
            if resp.status_code in [403, 401]:
                logger.warning(f"Token expired (status {resp.status_code}), refreshing again...")
                if self._get_csrf_token():
                    headers["X-CSRF-Token"] = self.csrf_token
                    resp = self.session.post(
                        f"{BASE_URL}/api/batch", 
                        headers=headers, 
                        json=payload,
                        stream=True,
                        timeout=30
                    )
                else:
                    return {vid: {"status": "error", "message": "Token expired and refresh failed"} for vid in verification_ids}

            # 检查响应状态
            if resp.status_code != 200:
                error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(f"Batch request failed: {error_msg}")
                return {vid: {"status": "error", "message": error_msg} for vid in verification_ids}

            # Parse SSE Stream
            # The API returns "data: {...json...}" lines
            for line in resp.iter_lines():
                if not line: continue
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data:"):
                    json_str = decoded_line[5:].strip()
                    try:
                        data = json.loads(json_str)
                        self._handle_api_response(data, results, callback)
                    except json.JSONDecodeError:
                        pass
                        
        except Exception as e:
            logger.error(f"Batch verify request failed: {e}")
            for vid in verification_ids:
                if vid not in results:
                    results[vid] = {"status": "error", "message": str(e)}

        return results

    def _handle_api_response(self, data, results, callback=None):
        """Handle individual data chunks from SSE or poll response"""
        vid = data.get("verificationId")
        if not vid: return

        status = data.get("currentStep")
        message = data.get("message", "")
        
        if callback:
            callback(vid, f"Step: {status} | Msg: {message}")

        bind_url = self._extract_bind_url(data)
        if bind_url:
            data["bindUrl"] = bind_url
            data["_bindUrl"] = bind_url

        if status == "pending" and "checkToken" in data:
            # Need to poll
            check_token = data["checkToken"]
            final_res = self._poll_status(check_token, vid, callback)
            bind_url = self._extract_bind_url(final_res)
            if bind_url:
                final_res["bindUrl"] = bind_url
                final_res["_bindUrl"] = bind_url
            results[vid] = final_res
        elif status == "success" or status == "error":
            # Done
            results[vid] = data

    def _poll_status(self, check_token, vid, callback=None):
        """Poll /api/check-status until success or error"""
        url = f"{BASE_URL}/api/check-status"
        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"
        
        # Poll max 60 times (approx 120s)
        for i in range(60):
            try:
                time.sleep(2)  # Wait 2s between polls
                payload = {"checkToken": check_token}
                
                # 增加超时时间到 30 秒，避免网络慢导致超时
                resp = self.session.post(url, headers=headers, json=payload, timeout=30)
                json_data = resp.json()
                
                status = json_data.get("currentStep")
                message = json_data.get("message", "")
                
                if callback:
                    callback(vid, f"Polling: {status} ({i+1}/60) | Msg: {message}")

                if status == "success" or status == "error":
                    bind_url = self._extract_bind_url(json_data)
                    if bind_url:
                        json_data["bindUrl"] = bind_url
                        json_data["_bindUrl"] = bind_url
                    return json_data
                
                # If pending, update checkToken if provided
                if "checkToken" in json_data:
                    check_token = json_data["checkToken"]
                    
            except requests.exceptions.Timeout as e:
                # 网络超时，继续重试
                logger.warning(f"Polling timeout (attempt {i+1}/60), retrying...")
                if callback:
                    callback(vid, f"Polling: timeout (retrying {i+1}/60)")
                continue
                
            except Exception as e:
                logger.error(f"Polling failed: {e}")
                # 其他错误，也继续重试而不是立即失败
                if callback:
                    callback(vid, f"Polling error: {str(e)[:50]} (retrying {i+1}/60)")
                continue
        
        return {"status": "error", "message": "Polling timeout (120s)"}

    def _extract_bind_url(self, data):
        if not data:
            return None
        preferred_keys = [
            "bindUrl", "bindingUrl", "offerUrl", "resultUrl", "redirectUrl",
            "returnUrl", "continueUrl", "nextUrl", "successUrl", "url", "link", "href"
        ]
        if isinstance(data, dict):
            for key in preferred_keys:
                val = data.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    return val

        urls = []

        def _collect(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    _collect(v)
            elif isinstance(obj, list):
                for v in obj:
                    _collect(v)
            elif isinstance(obj, str):
                for match in re.findall(r'https?://[^\\s"\'<>]+', obj):
                    urls.append(match)

        _collect(data)
        if not urls:
            return None

        prefer_hosts = [
            "one.google.com",
            "google.com/ai-student",
            "pay.google.com",
            "myaccount.google.com",
        ]
        for host in prefer_hosts:
            for url in urls:
                if host in url:
                    return url
        for url in urls:
            if "google.com" in url:
                return url
        return urls[0]

    def cancel_verification(self, verification_id):
        """Cancel a verification process"""
        if not self.csrf_token:
            if not self._get_csrf_token():
                return {"status": "error", "message": "No CSRF Token"}
        
        url = f"{BASE_URL}/api/cancel"
        headers = self.headers.copy()
        headers["X-CSRF-Token"] = self.csrf_token
        headers["Content-Type"] = "application/json"
        
        try:
            resp = self.session.post(url, headers=headers, json={"verificationId": verification_id}, timeout=10)
            try:
                return resp.json()
            except:
                return {"status": "error", "message": f"Invalid JSON: {resp.text}"}
        except Exception as e:
            logger.error(f"Cancel failed: {e}")
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    pass
