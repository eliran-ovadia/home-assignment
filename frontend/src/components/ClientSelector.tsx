// Dropdown over the active upload's clients. Counts in each option label so
// the user can pick high-activity clients without going through the table.
//
// `clients` and `loading` are owned by App.tsx — see the note there about
// avoiding duplicate /api/v1/clients fetches.

import { Card, Empty, Select, Typography } from "antd";
import { useMemo } from "react";
import type { ClientSummary } from "../types";

interface ClientSelectorProps {
  clients: ClientSummary[];
  loading: boolean;
  value: string | null;
  onChange: (clientId: string | null) => void;
}

export function ClientSelector({
  clients,
  loading,
  value,
  onChange,
}: ClientSelectorProps) {
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
          description={
            <Typography.Text type="secondary">No clients in the active upload</Typography.Text>
          }
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
