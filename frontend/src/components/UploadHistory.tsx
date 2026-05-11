// History table — every upload in the shared pool (ADR 016). The Load
// button calls PUT /users/me/last-viewed, so each user gets their own
// "currently viewing" pointer without affecting anyone else.

import { Button, Card, Tag, Table, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { listUploads, setLastViewedUpload } from "../api/client";
import type { UploadHistoryItem } from "../types";

interface UploadHistoryProps {
  refreshKey: number;
  onActivated: () => void;
}

export function UploadHistory({ refreshKey, onActivated }: UploadHistoryProps) {
  const [rows, setRows] = useState<UploadHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [switchingId, setSwitchingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listUploads()
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) message.error(`Failed to load uploads: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const handleLoad = async (uploadId: number) => {
    setSwitchingId(uploadId);
    try {
      await setLastViewedUpload(uploadId);
      message.success("Switched active upload");
      onActivated();
    } catch (err) {
      message.error(`Failed to switch upload: ${String(err)}`);
    } finally {
      setSwitchingId(null);
    }
  };

  return (
    <Card title="Upload history">
      <Table<UploadHistoryItem>
        size="small"
        loading={loading}
        rowKey="id"
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: "No uploads yet" }}
        columns={[
          { title: "ID", dataIndex: "id", key: "id", width: 60 },
          { title: "Filename", dataIndex: "filename", key: "filename" },
          {
            title: "Rows",
            dataIndex: "row_count",
            key: "row_count",
            width: 80,
            align: "right",
          },
          {
            title: "Violations",
            dataIndex: "violation_count",
            key: "violation_count",
            width: 100,
            align: "right",
          },
          {
            title: "Uploaded",
            dataIndex: "uploaded_at",
            key: "uploaded_at",
            render: (value: string) => new Date(value).toLocaleString(),
          },
          {
            title: "Status",
            key: "is_last_viewed",
            width: 140,
            render: (_: unknown, item: UploadHistoryItem) =>
              item.is_last_viewed ? (
                <Tag color="green">Currently viewing</Tag>
              ) : (
                <Typography.Text type="secondary">—</Typography.Text>
              ),
          },
          {
            title: "",
            key: "action",
            width: 100,
            render: (_: unknown, item: UploadHistoryItem) =>
              item.is_last_viewed ? null : (
                <Button
                  size="small"
                  loading={switchingId === item.id}
                  onClick={() => handleLoad(item.id)}
                >
                  Load
                </Button>
              ),
          },
        ]}
      />
    </Card>
  );
}
