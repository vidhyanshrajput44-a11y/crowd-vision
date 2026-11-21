export type WebSocketMessageHandler = (data: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private eventId: string | null = null;
  private handlers: Set<WebSocketMessageHandler> = new Set();
  private reconnectTimer: any = null;
  private isExplicitlyClosed = false;

  connect(eventId: string) {
    if (this.ws && this.eventId === eventId && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    this.disconnect();
    this.eventId = eventId;
    this.isExplicitlyClosed = false;

    const defaultWsHost = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
    const rawWs = (import.meta as any).env?.VITE_WS_BASE_URL || defaultWsHost;
    const baseWs = String(rawWs).replace(/\/$/, '');
    const wsUrl = `${baseWs}/ws/${eventId}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        // Connected
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handlers.forEach((handler) => handler(data));
        } catch {
          // ignore invalid json
        }
      };

      this.ws.onclose = () => {
        if (!this.isExplicitlyClosed) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer || this.isExplicitlyClosed || !this.eventId) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.eventId && !this.isExplicitlyClosed) {
        this.connect(this.eventId);
      }
    }, 3000);
  }

  disconnect() {
    this.isExplicitlyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.eventId = null;
  }

  subscribe(handler: WebSocketMessageHandler) {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }
}

export const wsClient = new WebSocketClient();
