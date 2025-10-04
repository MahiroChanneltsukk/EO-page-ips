#!/usr/bin/env python3
import ipaddress
import asyncio
import httpx
import time
from tqdm import tqdm
import os

async def check_ip(client, ip, semaphore):
    """检查单个IP是否返回404"""
    async with semaphore:
        try:
            response = await client.get(
                "https://api-edge-sakiko-dispatch-network-aws-cdn.dahi.edu.eu.org/",
                timeout=5,
                follow_redirects=True
            )
            if response.status_code == 404:
                return ip, True
        except Exception as e:
            pass
        return ip, False

async def scan_network(network_range, concurrency=500):
    """扫描网络段"""
    network = ipaddress.ip_network(network_range)
    ips = [str(ip) for ip in network.hosts()]
    
    print(f"🚀 开始扫描 {network_range}")
    print(f"📊 总IP数量: {len(ips)}")
    print(f"⚡ 并发数: {concurrency}")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    available_ips = []
    semaphore = asyncio.Semaphore(concurrency)
    
    # 配置HTTP客户端
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency
    )
    
    async with httpx.AsyncClient(
        limits=limits,
        verify=False,
        headers={
            'User-Agent': 'Mozilla/5.0 (compatible; GitHub-Actions-Scanner/1.0)'
        }
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
                
                # 每扫描1000个IP输出一次状态
                if completed % 1000 == 0:
                    print(f"📈 已扫描: {completed}/{len(ips)} | 可用IP: {len(available_ips)}")
    
    return available_ips

def main():
    start_time = time.time()
    
    # 配置参数 - 在GitHub Actions中适当降低并发数
    network_range = "43.174.0.0/15"
    concurrency = int(os.getenv('CONCURRENCY', '300'))  # 从环境变量获取并发数
    
    print("=" * 50)
    print("GitHub Actions IP扫描工具")
    print("=" * 50)
    
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
        
        print("\n" + "=" * 50)
        print("🎉 扫描完成!")
        print(f"⏱️  总耗时: {duration:.2f} 秒")
        print(f"📈 扫描速度: {len(available_ips)/duration:.2f} IP/秒")
        print(f"✅ 可用IP数量: {len(available_ips)}")
        print(f"💾 结果文件: available_ips.txt")
        
        # 显示前10个可用IP作为示例
        if available_ips:
            print(f"\n📋 前10个可用IP:")
            for ip in available_ips[:10]:
                print(f"  {ip}")
            if len(available_ips) > 10:
                print(f"  ... 还有 {len(available_ips) - 10} 个")
        
    except Exception as e:
        print(f"❌ 扫描过程中出现错误: {e}")
        raise

if __name__ == "__main__":
    main()
