import { io, Socket } from "socket.io-client";

type CreateFrappeSocketProps = {
  siteName: string;
  port?: string;
  protocol?: string;
  host?: string;
}

export function createFrappeSocket({ siteName, port = "9000", protocol, host }: CreateFrappeSocketProps): Socket {
  // Get protocol (http or https)
  protocol = protocol || window.location.protocol.replace(":", "");
  host = host || window.location.hostname;

  // Frappe socket.io URL format: protocol://host:port/siteName
  const url = `${protocol}://${host}:${port}/${siteName}`;

  console.log(`Connecting to socket.io at: ${url}`);

  const socket = io(url, {
    withCredentials: true,
    secure: protocol === "https",
    transports: ["websocket", "polling"], // Try websocket first, fallback to polling
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    reconnectionAttempts: 5,
  });

  return socket;
}