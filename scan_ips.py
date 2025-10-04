#!/usr/bin/env python3
import ipaddress
import asyncio
import httpx
import time
import os
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
        # 创建可复用的HTTP客户端
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
        """检查单个IP是否302重定向到目标URL"""
        async with semaphore:
            try:
                response = await self.client.get(
                    f"http://{ip}/",
                    headers={'Host': 'edgeone.app'}  # 只覆盖必要的头
                )
                
                # 检查是否是302重定向并且Location头匹配目标
                if (response.status_code == 302 and 
                    'Location' in response.headers and
                    response.headers['Location'] == 'https://edgeone.ai/products/pages'):
                    return ip, "可用"
                else:
                    return ip, "不可及"
                    
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, Exception):
                return ip, "不可及"

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
        if current_time - self.last_report_time >= 60:  # 每分钟报告一次
            self._report_progress(current_time)
            self.last_report_time = current_time
            self.last_completed = completed
    
    def final_report(self):
        """最终报告"""
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
        
        print(f"\n📊 进度报告 [{time.strftime('%H:%M:%S')}]")
        print(f"📈 已扫描: {self.completed}/{self.total_ips} ({self.completed/self.total_ips*100:.1f}%)")
        print(f"✅ 可用IP: {len(self.available_ips)}")
        print(f"❌ 不可及: {self.completed - len(self.available_ips)}")
        print(f"⚡ 近期速度: {recent_speed:.1f} IP/分钟")
        print(f"📊 平均速度: {avg_speed:.1f} IP/分钟")
        if eta_minutes > 0:
            print(f"⏱️  预计剩余: {eta_minutes:.1f} 分钟")
        print("-" * 50)

async def scan_network(network_range: str, concurrency: int = 300, timeout: float = 5.0) -> List[str]:
    """扫描网络段"""
    network = ipaddress.ip_network(network_range)
    ips = [str(ip) for ip in network.hosts()]
    
    print(f"🚀 开始扫描 {network_range}")
    print(f"📊 总IP数量: {len(ips)}")
    print(f"⚡ 并发数: {concurrency}")
    print(f"⏱️  超时时间: {timeout}秒")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 目标重定向: https://edgeone.ai/products/pages")
    print("-" * 60)
    
    available_ips = []
    semaphore = asyncio.Semaphore(concurrency)
    reporter = ProgressReporter(len(ips))
    
    async with IPScanner(concurrency, timeout) as scanner:
        tasks = [scanner.check_ip(ip, semaphore) for ip in ips]
        completed_count = 0
        
        for coro in asyncio.as_completed(tasks):
            ip, status = await coro
            completed_count += 1
            
            if status == "可用":
                available_ips.append(ip)
                print(f"✅ 可用IP: {ip}")
            
            # 更新进度
            reporter.update(completed_count, available_ips)
    
    # 最终报告
    reporter.final_report()
    return available_ips

def verify_redirects(ips: List[str], timeout: int = 5, max_workers: int = 10) -> List[str]:
    """批量验证IP的重定向是否正确"""
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
    print(f"\n🔍 开始验证 {len(ips)} 个IP的重定向...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(verify_single, ip): ip for ip in ips}
        
        for future in as_completed(future_to_ip):
            ip, is_valid = future.result()
            if is_valid:
                verified_ips.append(ip)
                print(f"✅ {ip} - 验证成功")
            else:
                print(f"❌ {ip} - 验证失败")
    
    return verified_ips

def save_results(ips: List[str], filename: str = "available_ips.txt"):
    """保存结果到文件"""
    with open(filename, "w") as f:
        for ip in ips:
            f.write(ip + "\n")
    print(f"💾 结果已保存到: {filename}")

def main():
    start_time = time.time()
    
    # 配置参数
    network_range = "43.174.0.0/15"
    concurrency = int(os.getenv('CONCURRENCY', '300'))
    timeout = float(os.getenv('TIMEOUT', '5.0'))
    
    print("=" * 60)
    print("GitHub Actions IP扫描工具 - 高性能复用版")
    print("=" * 60)
    print(f"🎯 目标域名: edgeone.app")
    print(f"🔄 期望重定向: https://edgeone.ai/products/pages")
    print(f"🌐 扫描网段: {network_range}")
    print(f"⚡ 并发数: {concurrency}")
    print(f"⏱️  超时时间: {timeout}秒")
    print("=" * 60)
    
    try:
        # 运行扫描
        available_ips = asyncio.run(scan_network(network_range, concurrency, timeout))
        
        # 按IP地址排序
        available_ips.sort(key=lambda ip: [int(part) for part in ip.split('.')])
        
        # 保存初步结果
        save_results(available_ips)
        
        # 批量验证
        if available_ips:
            verified_ips = verify_redirects(available_ips[:10], timeout)  # 只验证前10个作为样本
            save_results(verified_ips, "verified_ips.txt")
        
        # 输出统计信息
        end_time = time.time()
        duration = end_time - start_time
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        
        total_ips = len(list(ipaddress.ip_network(network_range).hosts()))
        
        print("\n" + "=" * 60)
        print("🎉 扫描完成!")
        print(f"⏱️  总耗时: {int(hours)}时{int(minutes)}分{seconds:.1f}秒")
        print(f"📊 总IP数量: {total_ips}")
        print(f"✅ 可用IP数量: {len(available_ips)}")
        print(f"❌ 不可及IP数量: {total_ips - len(available_ips)}")
        print(f"📈 可用率: {len(available_ips)/total_ips*100:.4f}%")
        print(f"⚡ 平均速度: {total_ips/max(duration/60, 0.1):.1f} IP/分钟")
        print(f"💾 结果文件: available_ips.txt")
        
        # 显示可用IP
        if available_ips:
            print(f"\n📋 前10个可用IP:")
            for ip in available_ips[:10]:
                print(f"  {ip}")
            
            if len(available_ips) > 10:
                print(f"  ... 还有 {len(available_ips) - 10} 个IP")
        else:
            print("\n❌ 未找到可用IP")
        
    except Exception as e:
        print(f"❌ 扫描过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
