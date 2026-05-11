// Analytics dashboard. Four required panels in a 2×2 grid; bonus block
// rendered as a row of cards when the API returns it (SPEC §4 says the
// `bonus` key is omitted if there is no data to populate it).

import { Card, Col, Empty, Row, Statistic, Table, Tag, message } from "antd";
import { useEffect, useState } from "react";
import { getAnalytics } from "../api/client";
import type {
  AnalyticsResponse,
  HoldingTimeEntry,
  IsinConcentrationEntry,
  TopTradedIsin,
  WinRateEntry,
} from "../types";

interface AnalyticsPanelProps {
  refreshKey: number;
}

function formatHoldingDays(value: string | null): string {
  return value === null ? "—" : `${parseFloat(value).toFixed(2)} days`;
}

export function AnalyticsPanel({ refreshKey }: AnalyticsPanelProps) {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAnalytics()
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((err: unknown) => {
        if (!cancelled) message.error(`Failed to load analytics: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (!data) {
    return (
      <Card title="Analytics" loading={loading}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No analytics data" />
      </Card>
    );
  }

  return (
    <Card title="Analytics" loading={loading}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card type="inner" title="Top 3 most traded ISINs">
            <Table<TopTradedIsin>
              size="small"
              rowKey="isin"
              pagination={false}
              dataSource={data.top_traded_isins}
              locale={{ emptyText: "No transactions" }}
              columns={[
                { title: "ISIN", dataIndex: "isin", key: "isin" },
                {
                  title: "Transactions",
                  dataIndex: "transaction_count",
                  key: "transaction_count",
                  align: "right",
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card type="inner" title="Average holding time per client">
            <Table<HoldingTimeEntry>
              size="small"
              rowKey="client_id"
              pagination={false}
              dataSource={data.avg_holding_time_per_client}
              locale={{ emptyText: "No completed trades" }}
              columns={[
                { title: "Client", dataIndex: "client_id", key: "client_id" },
                {
                  title: "Avg holding",
                  dataIndex: "avg_holding_days",
                  key: "avg_holding_days",
                  align: "right",
                  render: formatHoldingDays,
                },
              ]}
            />
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card type="inner" title="Most volatile client">
            {data.most_volatile_client ? (
              <>
                <Statistic
                  title="Client"
                  value={data.most_volatile_client.client_id}
                />
                <Row gutter={16} style={{ marginTop: 16 }}>
                  <Col span={8}>
                    <Statistic
                      title="Min value"
                      value={parseFloat(data.most_volatile_client.min_portfolio_value)}
                      precision={2}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Max value"
                      value={parseFloat(data.most_volatile_client.max_portfolio_value)}
                      precision={2}
                    />
                  </Col>
                  <Col span={8}>
                    <Statistic
                      title="Range"
                      value={parseFloat(data.most_volatile_client.value_range)}
                      precision={2}
                    />
                  </Col>
                </Row>
              </>
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No data yet"
              />
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card type="inner" title="ISIN concentration (held by > 70% of clients)">
            <Table<IsinConcentrationEntry>
              size="small"
              rowKey="isin"
              pagination={false}
              dataSource={data.isin_concentration}
              locale={{ emptyText: "No ISIN crosses the 70% threshold" }}
              columns={[
                { title: "ISIN", dataIndex: "isin", key: "isin" },
                {
                  title: "Clients",
                  key: "ratio",
                  align: "right",
                  render: (_: unknown, row: IsinConcentrationEntry) =>
                    `${row.client_count}/${row.total_clients} (${(row.concentration_pct * 100).toFixed(0)}%)`,
                },
                {
                  title: "Held by",
                  dataIndex: "clients",
                  key: "clients",
                  render: (clients: string[]) => (
                    <>
                      {clients.map((c) => (
                        <Tag key={c}>{c}</Tag>
                      ))}
                    </>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      {data.bonus && (
        <>
          <Card.Meta style={{ marginTop: 24 }} description="Bonus analytics" />
          <Row gutter={[16, 16]} style={{ marginTop: 12 }}>
            {data.bonus.top_realized_pnl_client && (
              <Col xs={24} md={8}>
                <Card type="inner" title="Top realized P&L client">
                  <Statistic
                    title={data.bonus.top_realized_pnl_client.client_id}
                    value={parseFloat(data.bonus.top_realized_pnl_client.realized_pnl)}
                    precision={2}
                    valueStyle={{ color: "#52c41a" }}
                  />
                </Card>
              </Col>
            )}
            {data.bonus.most_traded_day && (
              <Col xs={24} md={8}>
                <Card type="inner" title="Most traded day">
                  <Statistic
                    title={data.bonus.most_traded_day.date}
                    value={data.bonus.most_traded_day.transaction_count}
                    suffix="transactions"
                  />
                </Card>
              </Col>
            )}
            {data.bonus.win_rate_per_client.length > 0 && (
              <Col xs={24} md={8}>
                <Card type="inner" title="Win rate per client">
                  <Table<WinRateEntry>
                    size="small"
                    rowKey="client_id"
                    pagination={false}
                    dataSource={data.bonus.win_rate_per_client}
                    columns={[
                      { title: "Client", dataIndex: "client_id", key: "client_id" },
                      {
                        title: "Win rate",
                        dataIndex: "win_rate",
                        key: "win_rate",
                        align: "right",
                        render: (v: number) => `${(v * 100).toFixed(0)}%`,
                      },
                      {
                        title: "W / T",
                        key: "ratio",
                        align: "right",
                        render: (_: unknown, row: WinRateEntry) =>
                          `${row.winning_trades} / ${row.total_trades}`,
                      },
                    ]}
                  />
                </Card>
              </Col>
            )}
          </Row>
        </>
      )}
    </Card>
  );
}
