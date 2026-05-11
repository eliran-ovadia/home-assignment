// Dropdown over the active upload's clients. Counts in each option label so
// the user can pick high-activity clients without going through the table.

import { Card, Empty, Select, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { listClients } from "../api/client";
import type { ClientSummary } from "../types";

interface ClientSelectorProps {
  refreshKey: number;
  value: string | null;
  onChange: (clientId: string | null) => void;
}

export function ClientSelector({
  refreshKey,
  value,
  onChange,
}: ClientSelectorProps) {
  const [clients, setClients] = useState<ClientSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listClients()
      .then((data) => {
        if (!cancelled) setClients(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) message.error(`Failed to load clients: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const options = useMemo(
    () =>
      clients.map((c) => ({
        value: c.client_id,
        label: `${c.client_id}  ·  ${c.transaction_count} txns · ${c.position_count} positions · ${c.violation_count} violations`,
      })),
    [clients],
  );

  return (
    <Card title="Client">
      {clients.length === 0 && !loading ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={<Typography.Text type="secondary">No clients in the active upload</Typography.Text>}
        />
      ) : (
        <Select<string>
          style={{ width: "100%" }}
          placeholder="Select a client to inspect positions"
          loading={loading}
          options={options}
          value={value ?? undefined}
          onChange={(v) => onChange(v ?? null)}
          allowClear
          showSearch
          optionFilterProp="label"
        />
      )}
    </Card>
  );
}
