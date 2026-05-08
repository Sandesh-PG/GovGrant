import { CheckCircle2, Loader2, Circle } from 'lucide-react';
import { cn } from './StatusBadge';

interface AgentStatusCardProps {
  name: string;
  description: string;
  status: 'pending' | 'loading' | 'completed' | 'error';
  className?: string;
}

export function AgentStatusCard({ name, description, status, className }: AgentStatusCardProps) {
  return (
    <div
      className={cn(
        'flex items-center p-4 border rounded-xl transition-all duration-300',
        status === 'loading' ? 'bg-blue-50 border-blue-200 shadow-sm' : 
        status === 'completed' ? 'bg-green-50 border-green-200' : 'bg-white border-gray-100 opacity-60',
        className
      )}
    >
      <div className="mr-4">
        {status === 'loading' && <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />}
        {status === 'completed' && <CheckCircle2 className="w-6 h-6 text-green-500" />}
        {status === 'pending' && <Circle className="w-6 h-6 text-gray-300" />}
        {status === 'error' && <Circle className="w-6 h-6 text-red-500" />}
      </div>
      <div>
        <h3 className={cn(
          "font-semibold text-sm",
          status === 'loading' ? "text-blue-900" : 
          status === 'completed' ? "text-green-900" : "text-gray-500"
        )}>
          {name}
        </h3>
        <p className={cn(
          "text-xs",
          status === 'loading' ? "text-blue-700" : 
          status === 'completed' ? "text-green-700" : "text-gray-400"
        )}>
          {description}
        </p>
      </div>
    </div>
  );
}
