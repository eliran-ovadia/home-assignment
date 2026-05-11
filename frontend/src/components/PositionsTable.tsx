// Per-client positions. Money columns are right-aligned and P&L cells are
// color-coded (green for positive, red for negative, muted for zero).

import { Card, Table, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { getClientPositions } from "../api/client";
import type { PositionResponse } from "../types";

interface PositionsTableProps {
  clientId: string;
  refreshKey: number;
}

const MONEY_FORMATTER = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
});

function pnlColor(value: number): string | undefined {
  if (value > 0) return "#52c41a"; // antd green-6
  if (value < 0) return "#ff4d4f"; // antd red-5
  return undefined; // muted / default
}

function formatMoney(raw: string): string {
  return MONEY_FORMATTER.format(parseFloat(raw));
}

function pnlCell(raw: string) {
  const n = parseFloat(raw);
  return (
    <Typography.Text strong style={{ color: pnlColor(n) }}>
      {MONEY_FORMATTER.format(n)}
    </Typography.Text>
  );
}

export function PositionsTable({ clientId, refreshKey }: PositionsTableProps) {
  const [rows, setRows] = useState<PositionResponse[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getClientPositions(clientId)
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRows([]);
          message.error(`Failed to load positions: ${String(err)}`);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, refreshKey]);

  return (
    <Card title={`Positions — ${clientId}`}>
      <Table<PositionResponse>
        size="small"
        loading={loading}
        rowKey="isin"
        dataSource={rows}
        pagination={false}
        columns={[
          { title: "ISIN", dataIndex: "isin", key: "isin" },
          {
            title: "Quantity",
            dataIndex: "quantity",
            key: "quantity",
            align: "right",
            render: formatMoney,
          },
          {
            title: "Avg cost",
            dataIndex: "avg_cost",
            key: "avg_cost",
            align: "right",
            render: formatMoney,
          },
          {
            title: "Last price",
            dataIndex: "last_price",
            key: "last_price",
            align: "right",
            render: formatMoney,
          },
          {
            title: "Realized P&L",
            dataIndex: "realized_pnl",
            key: "realized_pnl",
            align: "right",
            render: pnlCell,
          },
          {
            title: "Unrealized P&L",
            dataIndex: "unrealized_pnl",
            key: "unrealized_pnl",
            align: "right",
            render: pnlCell,
          },
        ]}
      />
    </Card>
  );
}
