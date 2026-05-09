'use client';

import { useState } from 'react';
import { 
  ExternalLink, Calendar, TrendingUp, ChevronDown, ChevronUp, 
  CheckCircle2, FileText, ListChecks, Info, ClipboardCopy
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { RankedScheme, DocumentItem, ActionCard } from '@/lib/types';
import { cn } from '@/lib/utils';

interface GrantCardProps {
  scheme: RankedScheme;
  documents?: DocumentItem[];
  actionCard?: ActionCard;
}

export function GrantCard({ scheme, documents, actionCard }: GrantCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className={cn(
      "bg-white border transition-all duration-300 rounded-[2rem] overflow-hidden",
      isExpanded ? "border-blue-500 ring-4 ring-blue-500/5 shadow-xl" : "border-slate-100 shadow-sm hover:shadow-md"
    )}>
      {/* Header / Summary View */}
      <div className="p-8">
        <div className="flex justify-between items-start mb-6">
          <div className="flex-1 mr-4">
            <div className="flex items-center space-x-2 mb-2">
              <div className="px-2.5 py-0.5 bg-blue-50 text-blue-600 text-[10px] font-black uppercase tracking-widest rounded-md">
                Rank #{scheme.rank}
              </div>
              {scheme.urgency_score > 0.7 && (
                <div className="px-2.5 py-0.5 bg-orange-50 text-orange-600 text-[10px] font-black uppercase tracking-widest rounded-md flex items-center">
                   <ClockIcon size={10} className="mr-1" /> High Priority
                </div>
              )}
            </div>
            <h3 className="text-2xl font-black text-slate-900 leading-[1.1] mb-3">{scheme.scheme_name}</h3>
            
            <div className="flex flex-wrap items-center gap-4 text-sm text-slate-500 font-medium">
              {scheme.grant_amount && (
                <span className="flex items-center text-green-600 font-bold bg-green-50 px-3 py-1 rounded-full">
                  <TrendingUp size={14} className="mr-1.5" />
                  {scheme.grant_amount}
                </span>
              )}
              {scheme.deadline && (
                <span className="flex items-center bg-slate-50 px-3 py-1 rounded-full">
                  <Calendar size={14} className="mr-1.5 text-slate-400" />
                  {scheme.deadline}
                </span>
              )}
            </div>
          </div>
          <StatusBadge score={scheme.match_score} />
        </div>
        
        <p className="text-slate-600 leading-relaxed mb-8">
          {scheme.reason}
        </p>

        <div className="flex items-center justify-between pt-6 border-t border-slate-50">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className={cn(
              "flex items-center px-6 py-3 rounded-xl text-sm font-black transition-all",
              isExpanded 
                ? "bg-slate-900 text-white" 
                : "bg-slate-50 text-slate-900 hover:bg-slate-100"
            )}
          >
            {isExpanded ? (
              <>Hide Details <ChevronUp size={16} className="ml-2" /></>
            ) : (
              <>View Requirements & Roadmap <ChevronDown size={16} className="ml-2" /></>
            )}
          </button>
          
          {scheme.portal_url && (
            <a
              href={scheme.portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-blue-600 text-sm font-black hover:underline"
            >
              Official Portal
              <ExternalLink size={14} className="ml-1.5" />
            </a>
          )}
        </div>
      </div>

      {/* Expanded Details View */}
      {isExpanded && (
        <div className="bg-slate-50/50 border-t border-slate-100 p-8 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
            {/* Documents Section */}
            <div className="space-y-6">
              <div className="flex items-center space-x-2 text-slate-900">
                <FileText size={20} className="text-blue-500" />
                <h4 className="font-black uppercase tracking-widest text-xs">Required Documents</h4>
              </div>
              
              <div className="space-y-3">
                {documents && documents.length > 0 ? (
                  documents.map((doc, idx) => (
                    <div key={idx} className="flex items-start p-4 bg-white rounded-2xl border border-slate-100 shadow-sm">
                      <div className="w-5 h-5 rounded-md border-2 border-slate-200 mt-0.5 mr-3 flex-shrink-0" />
                      <div>
                        <p className="text-sm font-bold text-slate-800">
                          {doc.name}
                          {doc.mandatory && (
                            <span className="ml-2 text-[8px] bg-red-50 text-red-600 px-1.5 py-0.5 rounded font-black uppercase tracking-tighter">
                              Mandatory
                            </span>
                          )}
                        </p>
                        <p className="text-[11px] text-slate-500 mt-0.5">{doc.description}</p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-400 italic">No specific documents listed for this scheme.</p>
                )}
              </div>
            </div>

            {/* Roadmap / Action Card Section */}
            <div className="space-y-6">
              <div className="flex items-center space-x-2 text-slate-900">
                <ListChecks size={20} className="text-blue-500" />
                <h4 className="font-black uppercase tracking-widest text-xs">Application Roadmap</h4>
              </div>

              {actionCard ? (
                <div className="bg-white rounded-3xl p-6 border border-slate-100 shadow-sm relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-4">
                     <div className="px-3 py-1 bg-blue-600 text-white text-[10px] font-black rounded-lg">
                       {actionCard.estimated_days} Days Est.
                     </div>
                  </div>
                  
                  <div className="space-y-4">
                    {actionCard.steps.map((step, sidx) => (
                      <div key={sidx} className="flex items-start">
                        <div className="w-5 h-5 rounded-full bg-blue-100 text-blue-600 text-[10px] font-black flex items-center justify-center mt-0.5 mr-3 flex-shrink-0">
                          {sidx + 1}
                        </div>
                        <p className="text-sm text-slate-700 font-medium leading-tight">{step}</p>
                      </div>
                    ))}
                  </div>

                  {actionCard.tips && actionCard.tips.length > 0 && (
                    <div className="mt-8 pt-6 border-t border-slate-100">
                       <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3 flex items-center">
                         <Info size={12} className="mr-1" /> Pro Tips
                       </p>
                       <ul className="space-y-2">
                         {actionCard.tips.map((tip, tidx) => (
                           <li key={tidx} className="text-xs text-slate-600 flex items-start">
                             <CheckCircle2 size={12} className="text-green-500 mr-2 flex-shrink-0 mt-0.5" />
                             {tip}
                           </li>
                         ))}
                       </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-400 italic">Roadmap not available for this scheme.</p>
              )}
            </div>
          </div>
          
          <div className="mt-10 p-6 bg-blue-600/5 rounded-[2rem] border border-blue-500/10 flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-white rounded-xl shadow-sm text-blue-600">
                <ClipboardCopy size={20} />
              </div>
              <div>
                <p className="text-xs font-black text-slate-900 uppercase tracking-widest">Ready to apply?</p>
                <p className="text-sm text-slate-500 font-medium">Copy all requirements to your clipboard.</p>
              </div>
            </div>
            <button className="px-6 py-3 bg-blue-600 text-white text-sm font-black rounded-xl hover:bg-blue-500 transition-colors">
              Copy Checklist
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ClockIcon({ size, className }: { size: number, className: string }) {
  return (
    <svg 
      width={size} 
      height={size} 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="3" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      className={className}
    >
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}
