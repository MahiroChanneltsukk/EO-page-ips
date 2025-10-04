#!/usr/bin/env python3
import ipaddress
import asyncio
import httpx
import time
import os
import sys
from typing import List, Tuple

class IPScanner:
    def __init__(self, concurrency=300, timeout=5.0):
        self.concurrency = concurrency
        self.timeout = timeout
        self.client = None
        self.session_headers = {
            'Host': 'edgeone.app',
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
    async def __aenter__(self):
        # Create reusable HTTP client
        timeout_config = httpx.Timeout(self.timeout, connect=3.0)
        limits = httpx.Limits(
            max_connections=self.concurrency,
            max_keepalive_connections=self.concurrency // 2,
            keepalive_expiry=60.0
        )
        
        self.client = httpx.AsyncClient(
            timeout=timeout_config,
            verify=False,
            limits=limits,
            headers=self.session_headers,
            follow_redirects=False
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def check_ip(self, ip: str, semaphore: asyncio.Semaphore) -> Tuple[str, str]:
        """Check if a single IP redirects (302) to the target URL"""
        async with semaphore:
            try:
                response = await self.client.get(
                    f"http://{ip}/",
                    headers={'Host': 'edgeone.app'}
                )
                
                # Check if it's a 302 redirect with matching Location header
                if (response.status_code == 302 and 
                    'Location' in response.headers and
                    response.headers['Location'] == 'https://edgeone.ai/products/pages'):
                    return ip, "available"
                else:
                    return ip, "unreachable"
                    
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, Exception):
                return ip, "unreachable"

class ProgressReporter:
    def __init__(self, total_ips: int):
        self.total_ips = total_ips
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.last_completed = 0
        self.completed = 0
        self.available_ips = []
        
    def update(self, completed: int, available_ips: List[str]):
        self.completed = completed
        self.available_ips = available_ips.copy()
        
        current_time = time.time()
        if current_time - self.last_report_time >= 60:  # Report every minute
            self._report_progress(current_time)
            self.last_report_time = current_time
            self.last_completed = completed
    
    def final_report(self):
        """Final report"""
        current_time = time.time()
        self._report_progress(current_time)
    
    def _report_progress(self, current_time: float):
        elapsed_minutes = (current_time - self.last_report_time) / 60
        recent_completed = self.completed - self.last_completed
        recent_speed = recent_completed / elapsed_minutes if elapsed_minutes > 0 else 0
        
        total_elapsed = (current_time - self.start_time) / 60
        avg_speed = self.completed / total_elapsed if total_elapsed > 0 else 0
        
        remaining_ips = self.total_ips - self.completed
        eta_minutes = remaining_ips / max(avg_speed, 1) if avg_speed > 0 else 0
        
        # GitHub Actions-friendly output with explicit flushing
        print(f"\n::group::Progress Report [{time.strftime('%H:%M:%S')}]", flush=True)
        print(f"Scanned: {self.completed}/{self.total_ips} ({self.completed/self.total_ips*100:.1f}%)", flush=True)
        print(f"Available IPs: {len(self.available_ips)}", flush=True)
        print(f"Unreachable: {self.completed - len(self.available_ips)}", flush=True)
        print(f"Recent Speed: {recent_speed:.1f} IPs/min", flush=True)
        print(f"Average Speed: {avg_speed:.1f} IPs/min", flush=True)
        if eta_minutes > 0:
            print(f"ETA: {eta_minutes:.1f} minutes", flush=True)
        print("::endgroup::", flush=True)
        sys.stdout.flush()

async def scan_network(network_range: str, concurrency: int = 300, timeout: float = 5.0) -> List[str]:
    """Scan network range"""
    network = ipaddress.ip_network(network_range)
    ips = [str(ip) for ip in network.hosts()]
    
    print(f"Starting scan of {network_range}", flush=True)
    print(f"Total IPs: {len(ips)}", flush=True)
    print(f"Concurrency: {concurrency}", flush=True)
    print(f"Timeout: {timeout}s", flush=True)
    print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"Target Redirect: https://edgeone.ai/products/pages", flush=True)
    print("-" * 60, flush=True)
    sys.stdout.flush()
    
    available_ips = []
    semaphore = asyncio.Semaphore(concurrency)
    reporter = ProgressReporter(len(ips))
    
    async with IPScanner(concurrency, timeout) as scanner:
        tasks = [scanner.check_ip(ip, semaphore) for ip in ips]
        completed_count = 0
        
        for coro in asyncio.as_completed(tasks):
            ip, status = await coro
            completed_count += 1
            
            if status == "available":
                available_ips.append(ip)
                print(f"✓ Available IP: {ip}", flush=True)
                sys.stdout.flush()
            
            # Update progress
            reporter.update(completed_count, available_ips)
    
    # Final report
    reporter.final_report()
    return available_ips

def verify_redirects(ips: List[str], timeout: int = 5, max_workers: int = 10) -> List[str]:
    """Batch verify IP redirects"""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def verify_single(ip: str) -> Tuple[str, bool]:
        try:
            response = requests.get(
                f"http://{ip}/",
                headers={'Host': 'edgeone.app'},
                allow_redirects=False,
                timeout=timeout,
                verify=False
            )
            
            if response.status_code == 302 and 'Location' in response.headers:
                return ip, response.headers['Location'] == 'https://edgeone.ai/products/pages'
        except Exception:
            pass
        return ip, False
    
    verified_ips = []
    print(f"\nVerifying {len(ips)} IP redirects...", flush=True)
    sys.stdout.flush()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(verify_single, ip): ip for ip in ips}
        
        for future in as_completed(future_to_ip):
            ip, is_valid = future.result()
            if is_valid:
                verified_ips.append(ip)
                print(f"✓ {ip} - Verified", flush=True)
            else:
                print(f"✗ {ip} - Failed", flush=True)
            sys.stdout.flush()
    
    return verified_ips

def save_results(ips: List[str], filename: str = "available_ips.txt"):
    """Save results to file"""
    with open(filename, "w") as f:
        for ip in ips:
            f.write(ip + "\n")
    print(f"Results saved to: {filename}", flush=True)
    sys.stdout.flush()

def main():
    # Ensure unbuffered output for GitHub Actions
    sys.stdout.reconfigure(line_buffering=True)
    
    start_time = time.time()
    
    # Configuration
    network_range = "101.33.0.0/19"
    concurrency = int(os.getenv('CONCURRENCY', '300'))
    timeout = float(os.getenv('TIMEOUT', '5.0'))
    
    print("=" * 60, flush=True)
    print("GitHub Actions IP Scanner - High Performance", flush=True)
    print("=" * 60, flush=True)
    print(f"Target Domain: edgeone.app", flush=True)
    print(f"Expected Redirect: https://edgeone.ai/products/pages", flush=True)
    print(f"Scan Range: {network_range}", flush=True)
    print(f"Concurrency: {concurrency}", flush=True)
    print(f"Timeout: {timeout}s", flush=True)
    print("=" * 60, flush=True)
    sys.stdout.flush()
    
    try:
        # Run scan
        available_ips = asyncio.run(scan_network(network_range, concurrency, timeout))
        
        # Sort IPs
        available_ips.sort(key=lambda ip: [int(part) for part in ip.split('.')])
        
        # Save initial results
        save_results(available_ips)
        
        # Batch verification
        if available_ips:
            verified_ips = verify_redirects(available_ips[:10], timeout)  # Verify first 10 as sample
            save_results(verified_ips, "verified_ips.txt")
        
        # Output statistics
        end_time = time.time()
        duration = end_time - start_time
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        
        total_ips = len(list(ipaddress.ip_network(network_range).hosts()))
        
        print("\n" + "=" * 60, flush=True)
        print("Scan Complete!", flush=True)
        print(f"Total Time: {int(hours)}h {int(minutes)}m {seconds:.1f}s", flush=True)
        print(f"Total IPs: {total_ips}", flush=True)
        print(f"Available IPs: {len(available_ips)}", flush=True)
        print(f"Unreachable IPs: {total_ips - len(available_ips)}", flush=True)
        print(f"Success Rate: {len(available_ips)/total_ips*100:.4f}%", flush=True)
        print(f"Average Speed: {total_ips/max(duration/60, 0.1):.1f} IPs/min", flush=True)
        print(f"Results File: available_ips.txt", flush=True)
        
        # Display available IPs
        if available_ips:
            print(f"\nFirst 10 Available IPs:", flush=True)
            for ip in available_ips[:10]:
                print(f"  {ip}", flush=True)
            
            if len(available_ips) > 10:
                print(f"  ... and {len(available_ips) - 10} more", flush=True)
        else:
            print("\nNo available IPs found", flush=True)
        
        sys.stdout.flush()
        
    except Exception as e:
        print(f"Error during scan: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()

if __name__ == "__main__":
    main()
