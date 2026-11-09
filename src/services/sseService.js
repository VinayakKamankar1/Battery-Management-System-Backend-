/**
 * Server-Sent Events (SSE) Manager
 * Pushes real-time battery status and alert updates to connected frontend clients.
 */

const clients = new Set();

// Send periodic heartbeat every 20 seconds to keep connection alive
setInterval(() => {
  if (clients.size > 0) {
    for (const client of clients) {
      try {
        client.write(':ping\n\n');
      } catch (err) {
        clients.delete(client);
      }
    }
  }
}, 20000);

export const addSseClient = (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*',
  });

  // Initial connection confirmation event
  res.write(`event: connected\ndata: ${JSON.stringify({ message: 'SSE Stream Connected' })}\n\n`);

  clients.add(res);

  req.on('close', () => {
    clients.delete(res);
    res.end();
  });
};

export const broadcastSse = (event, data) => {
  if (clients.size === 0) return;

  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const client of clients) {
    try {
      client.write(payload);
    } catch (err) {
      clients.delete(client);
    }
  }
};

export const getConnectedClientsCount = () => clients.size;
