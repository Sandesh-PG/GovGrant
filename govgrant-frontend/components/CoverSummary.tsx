'use client';

import { useState } from 'react';
import { Copy, Check, FileText } from 'lucide-react';

interface CoverSummaryProps {
  summary: string;
}

export function CoverSummary({ summary }: CoverSummaryProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-white border border-blue-100 rounded-2xl overflow-hidden shadow-sm">
      <div className="bg-blue-50 px-6 py-4 border-b border-blue-100 flex items-center justify-between">
        <div className="flex items-center text-blue-900 font-bold">
          <FileText size={18} className="mr-2" />
          Cover Summary
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center text-xs font-semibold text-blue-700 bg-white px-3 py-1.5 rounded-lg border border-blue-200 hover:bg-blue-50 transition-colors"
        >
          {copied ? (
            <>
              <Check size={14} className="mr-1.5" />
              Copied!
            </>
          ) : (
            <>
              <Copy size={14} className="mr-1.5" />
              Copy to clipboard
            </>
          )}
        </button>
      </div>
      <div className="p-6">
        <p className="text-slate-700 text-sm leading-relaxed whitespace-pre-wrap font-serif">
          {summary}
        </p>
      </div>
      <div className="px-6 py-3 bg-slate-50 text-[10px] text-slate-400 border-t border-slate-100 uppercase tracking-widest text-center">
        Copy and adapt this summary for your grant applications
      </div>
    </div>
  );
}
