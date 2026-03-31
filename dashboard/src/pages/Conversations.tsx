import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft } from 'lucide-react';
import { useConversations } from '../hooks/useData';
import type { Conversation } from '../types';

function formatTime(ts: string) {
  if (!ts || ts === '-') return '-';
  return ts.replace('T', ' ').replace('Z', '').slice(0, 16);
}

function ConversationDetail({ conv, onBack }: { conv: Conversation; onBack: () => void }) {
  return (
    <div className="p-8 max-w-4xl">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 mb-6 transition-colors">
        <ArrowLeft size={14} /> 返回对话列表
      </button>

      <h2 className="text-xl font-semibold text-gray-900 mb-1">{conv.title}</h2>
      <p className="text-sm text-gray-500 mb-6">
        {conv.symbol} · {conv.source} · {formatTime(conv.timestamp_utc)}
      </p>

      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="prose text-sm text-gray-700">
          <ReactMarkdown>{conv.transcript || '暂无对话记录'}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function Conversations() {
  const { data, loading } = useConversations();
  const [selected, setSelected] = useState<number | null>(null);

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;
  if (selected !== null) return <ConversationDetail conv={data[selected]} onBack={() => setSelected(null)} />;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900">分析对话</h2>
        <p className="text-sm text-gray-500 mt-1">共 {data.length} 条归档</p>
      </div>

      <div className="space-y-3">
        {data.map((conv, i) => (
          <div
            key={conv.conversation_id + i}
            onClick={() => setSelected(i)}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:border-gray-300 cursor-pointer transition-all shadow-sm"
          >
            <div className="font-medium text-gray-900 text-sm">{conv.title}</div>
            <div className="text-xs text-gray-500 mt-1">
              {conv.symbol} · {conv.source} · {formatTime(conv.timestamp_utc)}
            </div>
          </div>
        ))}

        {data.length === 0 && (
          <div className="text-center text-gray-400 py-12 text-sm">暂无对话归档</div>
        )}
      </div>
    </div>
  );
}
