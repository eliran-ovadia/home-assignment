// Top-level layout. Holds:
//   - the active corporate email (drives the email-gate visibility)
//   - the active theme (dark or light)
//   - a `refreshKey` that components subscribe to via prop. Bumping the key
//     after an upload / last-viewed switch forces every child to re-fetch.
//   - the shared `clients` list. Two children need it (the dropdown and the
//     violations filter); fetching once here and passing as a prop avoids
//     the duplicate `/api/v1/clients` round-trip after every refresh.

import { BulbFilled, BulbOutlined, LogoutOutlined } from "@ant-design/icons";
import {
  Button,
  ConfigProvider,
  Layout,
  Space,
  Typography,
  theme as antdTheme,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import { clearStoredEmail, getStoredEmail, listClients } from "./api/client";
import { AnalyticsPanel } from "./components/AnalyticsPanel";
import { ClientSelector } from "./components/ClientSelector";
import { EmailGate } from "./components/EmailGate";
import { PositionsTable } from "./components/PositionsTable";
import { UploadHistory } from "./components/UploadHistory";
import { UploadSection } from "./components/UploadSection";
import { ViolationsTable } from "./components/ViolationsTable";
import type { ClientSummary } from "./types";

const THEME_STORAGE_KEY = "lumina:theme";
type Mode = "light" | "dark";

export function App() {
  const [email, setEmail] = useState<string | null>(() => getStoredEmail());
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem(THEME_STORAGE_KEY) as Mode | null) ?? "light",
  );
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedClient, setSelectedClient] = useState<string | null>(null);
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [clientsLoading, setClientsLoading] = useState(false);

  useEffect(() => {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  }, [mode]);

  // Single source of truth for the client list. Re-fetches whenever the
  // active upload changes (refreshKey) or the user signs in (email).
  // Without this hoist, ClientSelector and ViolationsTable would each call
  // /api/v1/clients independently on every refresh — two parallel requests
  // with identical responses.
  useEffect(() => {
    if (!email) return;
    let cancelled = false;
    setClientsLoading(true);
    listClients()
      .then((data) => {
        if (!cancelled) setClients(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.warn("Failed to load clients", err);
          setClients([]);
        }
      })
      .finally(() => {
        if (!cancelled) setClientsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [email, refreshKey]);

  const bumpRefresh = useCallback(() => {
    setRefreshKey((prev) => prev + 1);
    // Clear the client selection when the dataset changes — the previously
    // selected client may not exist in the new upload.
    setSelectedClient(null);
  }, []);

  const onLogout = () => {
    clearStoredEmail();
    setEmail(null);
  };

  const themeConfig = {
    algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  };

  // Email gate is rendered alone — no Layout, no data components — so the
  // children's useEffects don't fire unauthenticated requests before the
  // user has entered their email. The fetches would 400 anyway (no
  // X-Session-Token), but the network noise is avoidable.
  if (!email) {
    return (
      <ConfigProvider theme={themeConfig}>
        <EmailGate onSubmit={setEmail} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider theme={themeConfig}>
      <Layout style={{ minHeight: "100vh" }}>
        <Layout.Header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: mode === "dark" ? "#1f1f1f" : "#fff",
            borderBottom: `1px solid ${mode === "dark" ? "#303030" : "#f0f0f0"}`,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            Lumina Capital
          </Typography.Title>
          <Space>
            <Typography.Text type="secondary">{email}</Typography.Text>
            <Button
              type="text"
              icon={mode === "dark" ? <BulbFilled /> : <BulbOutlined />}
              onClick={() => setMode(mode === "dark" ? "light" : "dark")}
              aria-label="Toggle theme"
            />
            <Button
              type="text"
              icon={<LogoutOutlined />}
              onClick={onLogout}
              aria-label="Sign out"
            />
          </Space>
        </Layout.Header>

        <Layout.Content style={{ padding: 24, maxWidth: 1400, margin: "0 auto", width: "100%" }}>
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <UploadSection onUploaded={bumpRefresh} />
            <UploadHistory refreshKey={refreshKey} onActivated={bumpRefresh} />
            <ClientSelector
              clients={clients}
              loading={clientsLoading}
              value={selectedClient}
              onChange={setSelectedClient}
            />
            {selectedClient && (
              <PositionsTable clientId={selectedClient} refreshKey={refreshKey} />
            )}
            <ViolationsTable refreshKey={refreshKey} clients={clients} />
            <AnalyticsPanel refreshKey={refreshKey} />
          </Space>
        </Layout.Content>
      </Layout>
    </ConfigProvider>
  );
}
