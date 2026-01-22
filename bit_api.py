import requests
import json
import time
import functools
from typing import Callable, TypeVar, Any

# 官方文档地址
# https://doc2.bitbrowser.cn/jiekou/ben-di-fu-wu-zhi-nan.html

# 此demo仅作为参考使用，以下使用的指纹参数仅是部分参数，完整参数请参考文档

url = "http://127.0.0.1:54345"
headers = {'Content-Type': 'application/json'}
# 禁用代理，避免本地 API 请求被代理拦截
no_proxy = {'http': None, 'https': None}

T = TypeVar('T')


def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0) -> Callable:
    """
    简单的重试装饰器

    Args:
        max_attempts: 最大尝试次数
        delay: 初始延迟时间（秒）
        backoff: 延迟时间倍数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.Timeout,
                        requests.exceptions.ConnectionError) as e:
                    last_exception = e
                    if attempt < max_attempts:
                        print(f"[重试] {func.__name__} 第 {attempt} 次失败: {e}，{current_delay:.1f}s 后重试...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"[错误] {func.__name__} 达到最大重试次数 ({max_attempts})，放弃重试")

            raise last_exception
        return wrapper
    return decorator


@retry(max_attempts=3, delay=1.0)
def createBrowser():  # 创建或者更新窗口，指纹参数 browserFingerPrint 如没有特定需求，只需要指定下内核即可，如果需要更详细的参数，请参考文档
    json_data = {
        'name': 'google',  # 窗口名称
        'remark': '',  # 备注
        'proxyMethod': 2,  # 代理方式 2自定义 3 提取IP
        # 代理类型  ['noproxy', 'http', 'https', 'socks5', 'ssh']
        'proxyType': 'noproxy',
        'host': '',  # 代理主机
        'port': '',  # 代理端口
        'proxyUserName': '',  # 代理账号
        "browserFingerPrint": {  # 指纹对象
            'coreVersion': '124'  # 内核版本，注意，win7/win8/winserver 2012 已经不支持112及以上内核了，无法打开
        }
    }

    print("正在创建窗口...")
    res = requests.post(
        f"{url}/browser/update",
        json=json_data,
        headers=headers,
        timeout=10,
        proxies=no_proxy
    ).json()
    browserId = res['data']['id']
    print(f"窗口创建成功，ID: {browserId}")
    return browserId


def updateBrowser():  # 更新窗口，支持批量更新和按需更新，ids 传入数组，单独更新只传一个id即可，只传入需要修改的字段即可，比如修改备注，具体字段请参考文档，browserFingerPrint指纹对象不修改，则无需传入
    json_data = {'ids': ['93672cf112a044f08b653cab691216f0'],
                 'remark': '我是一个备注', 'browserFingerPrint': {}}
    res = requests.post(
        f"{url}/browser/update/partial",
        json=json_data,
        headers=headers,
        proxies=no_proxy
    ).json()
    print(res)


@retry(max_attempts=3, delay=1.0)
def openBrowser(id):  # 直接指定ID打开窗口，也可以使用 createBrowser 方法返回的ID
    json_data = {"id": f'{id}'}
    print(f"正在打开窗口 {id}...")
    res = requests.post(
        f"{url}/browser/open",
        json=json_data,
        headers=headers,
        timeout=30,
        proxies=no_proxy
    ).json()
    print(f"窗口打开响应: {res}")
    return res


@retry(max_attempts=2, delay=0.5)
def closeBrowser(id):  # 关闭窗口
    json_data = {'id': f'{id}'}
    print(f"正在关闭窗口 {id}...")
    res = requests.post(
        f"{url}/browser/close",
        json=json_data,
        headers=headers,
        timeout=10,
        proxies=no_proxy
    ).json()
    print(f"窗口关闭响应: {res}")


@retry(max_attempts=2, delay=0.5)
def deleteBrowser(id):  # 删除窗口
    json_data = {'id': f'{id}'}
    print(f"正在删除窗口 {id}...")
    res = requests.post(
        f"{url}/browser/delete",
        json=json_data,
        headers=headers,
        timeout=10,
        proxies=no_proxy
    ).json()
    print(f"窗口删除响应: {res}")


if __name__ == '__main__':
    try:
        browser_id = createBrowser()
        openBrowser(browser_id)

        print("\n等待10秒后自动关闭窗口...")
        time.sleep(10)  # 等待10秒自动关闭窗口

        closeBrowser(browser_id)

        print("\n等待10秒后自动删除窗口...")
        time.sleep(10)  # 等待10秒自动删掉窗口

        deleteBrowser(browser_id)
        print("\n程序执行完成！")
    except requests.exceptions.Timeout:
        print("\n[错误] 请求超时，请检查比特浏览器服务是否正常运行")
    except requests.exceptions.ConnectionError:
        print("\n[错误] 无法连接到比特浏览器API服务，请确保比特浏览器正在运行")
    except Exception as e:
        print(f"\n[错误] 发生异常: {e}")
        import traceback
        traceback.print_exc()
