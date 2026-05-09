import { Square, Info } from 'lucide-react';
import { DocumentItem, SchemeDocuments } from '@/lib/types';

interface ChecklistProps {
  documents?: DocumentItem[];
  documentsByScheme?: SchemeDocuments[];
}

const renderDocuments = (documents: DocumentItem[]) => (
  <div className="space-y-3">
    {documents.map((doc, i) => (
      <div key={i} className="flex items-start group">
        <div className="mt-1 mr-3 text-slate-300 group-hover:text-blue-500 transition-colors">
          <Square size={18} />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-800 leading-tight">
            {doc.name}
            {doc.mandatory && (
              <span className="ml-2 text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded uppercase tracking-tighter">
                Mandatory
              </span>
            )}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">{doc.description}</p>
        </div>
      </div>
    ))}
  </div>
);

export function Checklist({ documents, documentsByScheme }: ChecklistProps) {
  const hasSchemeDocs = Boolean(documentsByScheme && documentsByScheme.length > 0);
  const fallbackDocs = documents || [];

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6">
      <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center">
        Documents you&apos;ll need
      </h3>
      {hasSchemeDocs ? (
        <div className="space-y-6">
          {documentsByScheme!.map((group, i) => (
            <div key={`${group.scheme_name}-${i}`} className="space-y-3">
              <h4 className="text-sm font-bold text-slate-800">
                {group.scheme_name}
              </h4>
              {renderDocuments(group.documents)}
            </div>
          ))}
        </div>
      ) : fallbackDocs.length > 0 ? (
        renderDocuments(fallbackDocs)
      ) : (
        <p className="text-sm text-slate-500">No documents found yet.</p>
      )}
      <div className="mt-6 pt-4 border-t border-slate-200 flex items-start text-[11px] text-slate-500 italic">
        <Info size={14} className="mr-2 flex-shrink-0 mt-0.5" />
        <p>This checklist is generated from scheme portals and web sources when available. Always verify on the official portal.</p>
      </div>
    </div>
  );
}
