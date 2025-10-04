#!/usr/bin/env python3
import ipaddress
import asyncio
import httpx
import time
from tqdm import tqdm
import os

async def check_ip(client, ip, semaphore):
    """检查单个IP是否302重定向到目标URL"""
    async with semaphore:
        try:
            # 使用IP作为目标，设置Host头，并禁用自动重定向
            response = await client.get(
                f"http://{ip}/",
                timeout=2,
                follow_redirects=False,  # 禁用自动重定向，手动检查
                headers={
                    'Host': 'edgeone.app',
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
                }
            )
            
            # 检查是否是302重定向并且Location头匹配目标
            if (response.status_code == 302 and 
                'Location' in response.headers and
                response.headers['Location'] == 'https://edgeone.ai/products/pages'):
                return ip, True
                
        except Exception as e:
            pass
        return ip, False

async def scan_network(network_range, concurrency=300):
    """扫描网络段"""
    network = ipaddress.ip_network(network_range)
    ips = [str(ip) for ip in network.hosts()]
    
    print(f"🚀 开始扫描 {network_range}")
    print(f"📊 总IP数量: {len(ips)}")
    print(f"⚡ 并发数: {concurrency}")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 目标重定向: https://edgeone.ai/products/pages")
    
    available_ips = []
    semaphore = asyncio.Semaphore(concurrency)
    
    # 配置HTTP客户端
    timeout = httpx.Timeout(10.0, connect=5.0)
    
    async with httpx.AsyncClient(
        timeout=timeout,
        verify=False,
        limits=httpx.Limits(max_connections=concurrency)
    ) as client:
        tasks = [check_ip(client, ip, semaphore) for ip in ips]
        
        completed = 0
        with tqdm(total=len(tasks), desc="扫描进度") as pbar:
            for coro in asyncio.as_completed(tasks):
                ip, is_available = await coro
                if is_available:
                    available_ips.append(ip)
                    tqdm.write(f"✅ 可用IP: {ip}")
                completed += 1
                pbar.update(1)
                
                # 每扫描500个IP输出一次状态
                if completed % 500 == 0:
                    print(f"📈 已扫描: {completed}/{len(ips)} | 可用IP: {len(available_ips)}")
    
    return available_ips

def verify_redirect(ip):
    """验证单个IP的重定向是否正确"""
    import requests
    try:
        response = requests.get(
            f"https://{ip}/",
            headers={
                'Host': 'edgeone.app',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
            },
            allow_redirects=False,
            timeout=5,
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
    
    print("=" * 60)
    print("GitHub Actions IP扫描工具 - 302重定向检测版")
    print("=" * 60)
    print(f"🎯 目标域名: edgeone.app")
    print(f"🔄 期望重定向: https://edgeone.ai/products/pages")
    print(f"🌐 扫描网段: {network_range}")
    print("=" * 60)
    
    try:
        # 运行扫描
        available_ips = asyncio.run(scan_network(network_range, concurrency))
        
        # 按IP地址排序
        available_ips.sort(key=lambda ip: [int(part) for part in ip.split('.')])
        
        # 保存结果
        with open("available_ips.txt", "w") as f:
            for ip in available_ips:
                f.write(ip + "\n")
        
        # 输出统计信息
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print("🎉 扫描完成!")
        print(f"⏱️  总耗时: {duration:.2f} 秒")
        print(f"📈 扫描速度: {len(ips)/max(duration, 0.1):.2f} IP/秒")
        print(f"✅ 可用IP数量: {len(available_ips)}")
        print(f"💾 结果文件: available_ips.txt")
        
        # 显示可用IP并验证前几个
        if available_ips:
            print(f"\n📋 所有可用IP ({len(available_ips)}个):")
            for ip in available_ips:
                print(f"  {ip}")
            
            print(f"\n🔍 验证前3个IP的重定向:")
            for ip in available_ips[:3]:
                if verify_redirect(ip):
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
