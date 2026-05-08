import { CheckSquare, Square, Info } from 'lucide-react';
import { DocumentItem } from '@/lib/types';

interface ChecklistProps {
  documents: DocumentItem[];
}

export function Checklist({ documents }: ChecklistProps) {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
      <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center">
        Documents you&apos;ll need
      </h3>
      <div className="space-y-3">
        {documents.map((doc, i) => (
          <div key={i} className="flex items-start group">
            <div className="mt-1 mr-3 text-slate-300 group-hover:text-blue-500 transition-colors">
              <Square size={18} />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 leading-tight">
                {doc.name}
                {doc.mandatory && <span className="ml-2 text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded uppercase tracking-tighter">Mandatory</span>}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">{doc.description}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-6 pt-4 border-t border-slate-200 flex items-start text-[11px] text-slate-500 italic">
        <Info size={14} className="mr-2 flex-shrink-0 mt-0.5" />
        <p>This checklist is generated based on standard requirements for the matched schemes. Specific portal requirements may vary.</p>
      </div>
    </div>
  );
}
