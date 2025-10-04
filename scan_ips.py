#!/usr/bin/env python3
import ipaddress
import asyncio
import httpx
import time
import os

class IPScanner:
    def __init__(self, concurrency=300, timeout=5.0):
        self.concurrency = concurrency
        self.timeout = timeout
        self.client = None
        
    async def __aenter__(self):
        # 创建可复用的HTTP客户端
        timeout = httpx.Timeout(self.timeout, connect=3.0)
        self.client = httpx.AsyncClient(
            timeout=timeout,
            verify=False,
            limits=httpx.Limits(max_connections=self.concurrency),
            headers={
                'Host': 'edgeone.app',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def check_ip(self, ip, semaphore):
        """检查单个IP是否302重定向到目标URL"""
        async with semaphore:
            try:
                response = await self.client.get(
                    f"http://{ip}/",
                    follow_redirects=False  # 禁用自动重定向，手动检查
                )
                
                # 检查是否是302重定向并且Location头匹配目标
                if (response.status_code == 302 and 
                    'Location' in response.headers and
                    response.headers['Location'] == 'https://edgeone.ai/products/pages'):
                    return ip, "可用"
                else:
                    return ip, "不可及"
                    
            except Exception:
                return ip, "不可及"

async def scan_network(network_range, concurrency=300, timeout=5.0):
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
    
    async with IPScanner(concurrency, timeout) as scanner:
        tasks = [scanner.check_ip(ip, semaphore) for ip in ips]
        
        completed = 0
        last_report_time = time.time()
        last_completed = 0
        
        for coro in asyncio.as_completed(tasks):
            ip, status = await coro
            
            if status == "可用":
                available_ips.append(ip)
                print(f"✅ 可用IP: {ip}")
            
            completed += 1
            
            # 每分钟报告一次状态
            current_time = time.time()
            if current_time - last_report_time >= 60:  # 60秒 = 1分钟
                elapsed_minutes = (current_time - last_report_time) / 60
                recent_completed = completed - last_completed
                recent_speed = recent_completed / elapsed_minutes if elapsed_minutes > 0 else 0
                
                print(f"\n📊 进度报告 [{time.strftime('%H:%M:%S')}]")
                print(f"📈 已扫描: {completed}/{len(ips)} ({completed/len(ips)*100:.1f}%)")
                print(f"✅ 可用IP: {len(available_ips)}")
                print(f"❌ 不可及: {completed - len(available_ips)}")
                print(f"⚡ 近期速度: {recent_speed:.1f} IP/分钟")
                print(f"⏱️  预计剩余: {(len(ips)-completed)/max(recent_speed,1):.1f} 分钟")
                print("-" * 40)
                
                last_report_time = current_time
                last_completed = completed
    
    return available_ips

def verify_redirect(ip, timeout=5):
    """验证单个IP的重定向是否正确"""
    import requests
    try:
        response = requests.get(
            f"http://{ip}/",
            headers={
                'Host': 'edgeone.app',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
            },
            allow_redirects=False,
            timeout=timeout,
            verify=False
        )
        
        if response.status_code == 302 and 'Location' in response.headers:
            print(f"🔍 验证 {ip}: 状态码={response.status_code}, Location={response.headers['Location']}")
            return response.headers['Location'] == 'https://edgeone.ai/products/pages'
    except Exception as e:
        print(f"🔍 验证 {ip} 失败: {e}")
    
    return False

def main():
    start_time = time.time()
    
    # 配置参数
    network_range = "43.174.0.0/15"
    concurrency = int(os.getenv('CONCURRENCY', '300'))
    timeout = float(os.getenv('TIMEOUT', '5.0'))
    
    print("=" * 60)
    print("GitHub Actions IP扫描工具 - 优化版")
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
        
        # 保存结果
        with open("available_ips.txt", "w") as f:
            for ip in available_ips:
                f.write(ip + "\n")
        
        # 输出统计信息
        end_time = time.time()
        duration = end_time - start_time
        minutes, seconds = divmod(duration, 60)
        
        print("\n" + "=" * 60)
        print("🎉 扫描完成!")
        print(f"⏱️  总耗时: {int(minutes)}分{seconds:.1f}秒")
        print(f"📈 平均速度: {len(available_ips)/max(duration/60, 0.1):.1f} IP/分钟")
        print(f"✅ 可用IP数量: {len(available_ips)}")
        print(f"❌ 不可及IP数量: {len(ipaddress.ip_network(network_range).hosts()) - len(available_ips)}")
        print(f"📊 可用率: {len(available_ips)/len(ipaddress.ip_network(network_range).hosts())*100:.2f}%")
        print(f"💾 结果文件: available_ips.txt")
        
        # 显示可用IP并验证前几个
        if available_ips:
            print(f"\n📋 前10个可用IP:")
            for ip in available_ips[:10]:
                print(f"  {ip}")
            
            if len(available_ips) > 10:
                print(f"  ... 还有 {len(available_ips) - 10} 个IP")
            
            print(f"\n🔍 验证前3个IP的重定向:")
            for ip in available_ips[:3]:
                if verify_redirect(ip, timeout):
                    print(f"  ✅ {ip} - 重定向验证成功")
                else:
                    print(f"  ❌ {ip} - 重定向验证失败")
        else:
            print("\n❌ 未找到可用IP")
        
    except Exception as e:
        print(f"❌ 扫描过程中出现错误: {e}")
        raise

if __name__ == "__main__":
    main()
