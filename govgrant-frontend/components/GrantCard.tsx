import { ExternalLink, Calendar, TrendingUp } from 'lucide-react';
import { StatusBadge } from './StatusBadge';
import { RankedScheme } from '@/lib/types';

interface GrantCardProps {
  scheme: RankedScheme;
}

export function GrantCard({ scheme }: GrantCardProps) {
  return (
    <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-bold text-slate-900 leading-tight mb-1">{scheme.scheme_name}</h3>
          <div className="flex items-center space-x-3 text-sm text-slate-500">
            {scheme.grant_amount && (
              <span className="flex items-center">
                <TrendingUp size={14} className="mr-1 text-green-600" />
                {scheme.grant_amount}
              </span>
            )}
            {scheme.deadline && (
              <span className="flex items-center">
                <Calendar size={14} className="mr-1 text-slate-400" />
                {scheme.deadline}
              </span>
            )}
          </div>
        </div>
        <StatusBadge score={scheme.match_score} />
      </div>
      
      <p className="text-slate-600 text-sm mb-6 leading-relaxed">
        {scheme.reason}
      </p>

      <div className="flex items-center justify-between mt-auto pt-4 border-t border-slate-50">
        <div className="flex items-center text-xs font-medium text-slate-400 uppercase tracking-wider">
          Rank #{scheme.rank} Match
        </div>
        {scheme.portal_url && (
          <a
            href={scheme.portal_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center px-4 py-2 bg-blue-50 text-blue-700 text-sm font-semibold rounded-xl hover:bg-blue-100 transition-colors"
          >
            Apply now
            <ExternalLink size={14} className="ml-2" />
          </a>
        )}
      </div>
    </div>
  );
}
