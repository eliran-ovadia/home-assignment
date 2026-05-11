// Violations table with two filter selects (type, client). Severity is
// rendered as a colored tag — ERROR red, WARNING orange, FLAG yellow.
//
// `clients` is owned by App.tsx — we receive it as a prop so the
// /api/v1/clients call isn't duplicated by ClientSelector and this
// component both fetching it independently after each refresh.

import { Card, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { listViolations } from "../api/client";
import type { ClientSummary, ViolationResponse } from "../types";

const VIOLATION_TYPES = ["SELL_BEFORE_BUY", "DAY_TRADING", "RISK_CONCENTRATION"] as const;

function severityTag(severity: string) {
  switch (severity) {
    case "ERROR":
      return <Tag color="red">ERROR</Tag>;
    case "WARNING":
      return <Tag color="orange">WARNING</Tag>;
    case "FLAG":
      return <Tag color="gold">FLAG</Tag>;
    default:
      return <Tag>{severity}</Tag>;
  }
}

interface ViolationsTableProps {
  refreshKey: number;
  clients: ClientSummary[];
}

export function ViolationsTable({ refreshKey, clients }: ViolationsTableProps) {
  const [rows, setRows] = useState<ViolationResponse[]>([]);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [clientFilter, setClientFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listViolations({
      client_id: clientFilter ?? undefined,
      violation_type: typeFilter ?? undefined,
    })
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) message.error(`Failed to load violations: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, clientFilter, typeFilter]);

  const clientOptions = useMemo(
    () => clients.map((c) => ({ value: c.client_id, label: c.client_id })),
    [clients],
  );

  return (
    <Card title="Violations">
      <Space style={{ marginBottom: 12 }}>
        <Select<string>
          placeholder="Filter by type"
          allowClear
          style={{ width: 240 }}
          value={typeFilter ?? undefined}
          onChange={(v) => setTypeFilter(v ?? null)}
          options={VIOLATION_TYPES.map((t) => ({ value: t, label: t }))}
        />
        <Select<string>
          placeholder="Filter by client"
          allowClear
          showSearch
          optionFilterProp="label"
          style={{ width: 240 }}
          value={clientFilter ?? undefined}
          onChange={(v) => setClientFilter(v ?? null)}
          options={clientOptions}
        />
      </Space>
      <Table<ViolationResponse>
        size="small"
        loading={loading}
        rowKey="id"
        dataSource={rows}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        columns={[
          {
            title: "Type",
            dataIndex: "violation_type",
            key: "violation_type",
            width: 200,
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: "Severity",
            dataIndex: "severity",
            key: "severity",
            width: 110,
            render: severityTag,
          },
          { title: "Client", dataIndex: "client_id", key: "client_id", width: 100 },
          {
            title: "ISIN",
            dataIndex: "isin",
            key: "isin",
            width: 140,
            render: (v: string | null) =>
              v ?? <Typography.Text type="secondary">—</Typography.Text>,
          },
          {
            title: "Transaction",
            dataIndex: "transaction_id",
            key: "transaction_id",
            width: 140,
            render: (v: string | null) =>
              v ?? <Typography.Text type="secondary">—</Typography.Text>,
          },
          { title: "Description", dataIndex: "description", key: "description" },
        ]}
      />
    </Card>
  );
}
