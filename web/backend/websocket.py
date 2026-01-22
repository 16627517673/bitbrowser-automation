"""
WebSocket 管理模块
用于实时推送任务进度和日志
"""
import asyncio
import json
from typing import List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# 最大连接数限制
MAX_CONNECTIONS = 50


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> bool:
        """
        接受新连接

        Returns:
            是否成功接受连接（超过限制时返回 False）
        """
        if len(self.active_connections) >= MAX_CONNECTIONS:
            print(f"[WS] 连接数已达上限 ({MAX_CONNECTIONS})，拒绝新连接")
            await websocket.close(code=1013, reason="Max connections reached")
            return False

        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] 新连接，当前连接数: {len(self.active_connections)}")
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] 断开连接，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """广播消息给所有连接"""
        if not self.active_connections:
            return

        text = json.dumps(message, ensure_ascii=False)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(text)
            except Exception:
                disconnected.append(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

    async def send_task_progress(self, task_id: str, task_type: str,
                                  status: str, total: int, completed: int,
                                  current_email: str = None, message: str = None):
        """发送任务进度"""
        await self.broadcast({
            "type": "task_progress",
            "data": {
                "task_id": task_id,
                "task_type": task_type,
                "status": status,
                "total": total,
                "completed": completed,
                "current_email": current_email,
                "message": message,
            }
        })

    async def send_log(self, level: str, message: str, email: str = None):
        """发送日志消息"""
        await self.broadcast({
            "type": "log",
            "data": {
                "level": level,
                "message": message,
                "email": email,
            }
        })

    async def send_account_progress(
        self,
        task_id: str,
        email: str,
        status: str,
        current_task: str = None,
        message: str = None,
        total: int = 0,
        completed: int = 0,
        failed: int = 0,
    ):
        """发送单个账号的执行进度"""
        await self.broadcast({
            "type": "account_progress",
            "data": {
                "task_id": task_id,
                "email": email,
                "status": status,
                "current_task": current_task,
                "message": message,
                "total": total,
                "completed": completed,
                "failed": failed,
            }
        })


# 全局连接管理器实例
manager = ConnectionManager()


def get_manager() -> ConnectionManager:
    """获取连接管理器实例"""
    return manager


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    connected = await manager.connect(websocket)
    if not connected:
        return

    try:
        while True:
            # 保持连接，接收心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
