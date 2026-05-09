'use client';

import Link from 'next/link';
import {
  ArrowRight, CheckCircle2, Shield, Zap, TrendingUp,
  Globe, Sparkles, Layout, Database, Search,
  FileText, CheckCircle, BarChart3, Clock, Lock
} from 'lucide-react';
import { cn } from '@/lib/utils';

export default function LandingPage() {
  return (
    <div className="flex flex-col min-h-screen selection:bg-blue-500/30 bg-[#020617]">
      {/* Background Orbs - More intense and dynamic */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-600/15 rounded-full blur-[140px] animate-blob" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] bg-indigo-600/15 rounded-full blur-[140px] animate-blob animation-delay-2000" />
        <div className="absolute top-[30%] right-[-5%] w-[40%] h-[40%] bg-purple-600/10 rounded-full blur-[120px] animate-blob animation-delay-4000" />
      </div>

      {/* Navbar - Ultra Glass */}
      <nav className="flex items-center justify-between px-6 md:px-12 py-5 glass sticky top-0 z-50 border-b border-white/5 backdrop-blur-2xl">
        <div className="flex items-center space-x-3 group cursor-pointer">
          <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl shadow-lg shadow-blue-500/30 group-hover:rotate-6 transition-all">
            <Shield className="text-white w-5 h-5" />
          </div>
          <span className="font-outfit font-black text-2xl tracking-tight text-white">
            GovGrant<span className="text-blue-500">.</span>
          </span>
        </div>

        <div className="hidden lg:flex items-center space-x-10 text-sm font-bold uppercase tracking-widest text-slate-400">
          <Link href="#how-it-works" className="hover:text-blue-500 transition-colors">Process</Link>
          <Link href="#features" className="hover:text-blue-500 transition-colors">Capability</Link>
          <Link href="#schemes" className="hover:text-blue-500 transition-colors">Live Data</Link>
        </div>

        <div className="flex items-center space-x-5">
          <Link href="/login" className="hidden sm:block text-sm font-bold text-slate-400 hover:text-white transition-colors">
            Sign In
          </Link>
          <Link href="/register" className="px-7 py-3 bg-white text-slate-900 text-sm font-black rounded-xl hover:bg-blue-500 hover:text-white transition-all shadow-[0_0_20px_rgba(255,255,255,0.1)] active:scale-95">
            Get Started Free
          </Link>
        </div>
      </nav>

      {/* Hero Section - High Impact */}
      <section className="relative px-6 pt-28 pb-40 max-w-7xl mx-auto text-center">
        <div className="inline-flex items-center px-4 py-1.5 glass rounded-full mb-12 border border-blue-500/30 animate-float">
          <Sparkles size={14} className="text-blue-400 mr-2" />
          <span className="text-[10px] font-black tracking-[0.2em] uppercase text-blue-400">
            Powered by Gemini 2.0 Flash Agentic Pipeline
          </span>
        </div>

        <h1 className="font-outfit text-6xl md:text-[100px] font-black text-white tracking-tighter leading-[0.95] mb-10">
          Unlock the grants your <br />
          business <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-blue-500 to-indigo-500 drop-shadow-[0_0_30px_rgba(59,130,246,0.5)]">deserves.</span>
        </h1>

        <p className="text-xl md:text-3xl text-slate-400 max-w-4xl mx-auto mb-16 leading-snug font-medium">
          The first AI-agent pipeline that scans the entire Indian grant ecosystem <br className="hidden md:block" />
          to find your perfect match in 30 seconds.
        </p>

        <div className="flex flex-col items-center gap-10">
          <Link href="/chat" className="w-full md:w-auto px-12 py-6 bg-blue-600 text-white text-2xl font-black rounded-[2rem] hover:bg-blue-500 hover:scale-105 hover:shadow-[0_0_50px_rgba(37,99,235,0.4)] transition-all flex items-center justify-center group relative overflow-hidden">
            <span className="relative z-10 flex items-center">
              Start Free Discovery
              <ArrowRight className="ml-3 group-hover:translate-x-2 transition-transform" />
            </span>
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
          </Link>

          <div className="flex flex-wrap justify-center items-center gap-8 text-slate-500 font-bold uppercase text-[10px] tracking-[0.3em]">
            <div className="flex items-center"><CheckCircle2 size={16} className="text-blue-500 mr-2" /> No Credit Card</div>
            <div className="flex items-center"><CheckCircle2 size={16} className="text-blue-500 mr-2" /> 100% Secure</div>
            <div className="flex items-center"><CheckCircle2 size={16} className="text-blue-500 mr-2" /> Real-time Data</div>
          </div>
        </div>
      </section>

      {/* Live Data / Stats Showcase */}
      <section className="pb-32 px-6">
        <div className="max-w-7xl mx-auto glass rounded-[4rem] p-12 md:p-20 border border-white/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/5 rounded-full blur-3xl -mr-48 -mt-48" />

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-16 relative z-10">
            {[
              { val: "100+", label: "ACTIVE SCHEMES", icon: <Database /> },
              { val: "₹5Cr", label: "MAX GRANT VALUE", icon: <TrendingUp /> },
              { val: "30s", label: "AVG. DISCOVERY TIME", icon: <Clock /> },
              { val: "98%", label: "MATCH ACCURACY", icon: <Zap /> },
            ].map((stat, i) => (
              <div key={stat.label} className="flex flex-col items-center md:items-start">
                <div className="text-blue-500 mb-4">{stat.icon}</div>
                <div className="text-5xl font-black text-white mb-2">{stat.val}</div>
                <div className="text-[10px] font-black tracking-[0.2em] text-slate-500">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* The Pipeline Visualization */}
      <section id="how-it-works" className="py-32 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col items-center mb-24">
            <span className="text-blue-500 font-black text-xs tracking-[0.4em] uppercase mb-4">The GovGrant Engine</span>
            <h2 className="font-outfit text-4xl md:text-6xl font-black text-center text-white mb-8">
              Four Agents. One Goal.
            </h2>
            <p className="text-slate-400 text-center max-w-2xl text-lg">
              Our proprietary pipeline chains four specialized AI agents together to deliver professional-grade grant research in seconds.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {[
              { name: "Intake Agent", desc: "Conversational data gathering & profile building.", color: "blue" },
              { name: "Research Agent", desc: "Live web-scraping & RAG-based scheme matching.", color: "indigo" },
              { name: "Validator Agent", desc: "Strict eligibility checking & scoring.", color: "purple" },
              { name: "Planner Agent", desc: "Report generation & actionable roadmaps.", color: "pink" }
            ].map((agent, i) => (
              <div key={agent.name} className="group p-8 glass rounded-3xl border border-white/5 hover:bg-white/5 transition-all">
                <div className={cn(
                  "w-12 h-12 rounded-2xl flex items-center justify-center mb-8 shadow-lg",
                  i === 0 ? "bg-blue-500/20 text-blue-400" :
                    i === 1 ? "bg-indigo-500/20 text-indigo-400" :
                      i === 2 ? "bg-purple-500/20 text-purple-400" :
                        "bg-pink-500/20 text-pink-400"
                )}>
                  {i === 0 ? <Sparkles /> : i === 1 ? <Search /> : i === 2 ? <CheckCircle /> : <FileText />}
                </div>
                <h3 className="text-xl font-black text-white mb-3">{agent.name}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{agent.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Featured Schemes Mockup */}
      <section id="schemes" className="py-32 px-6 bg-blue-600/5 border-y border-white/5">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-end mb-16 gap-8">
            <div className="max-w-2xl text-left">
              <h2 className="text-4xl md:text-5xl font-black text-white mb-6">Live Scheme Tracker</h2>
              <p className="text-slate-400 text-lg">Daily updated database of schemes from the Gazette of India and state notifications.</p>
            </div>
            <div className="flex gap-4">
              <div className="px-6 py-3 glass rounded-xl border border-white/10 text-white text-sm font-bold">104 Total</div>
              <div className="px-6 py-3 bg-green-500/10 rounded-xl border border-green-500/20 text-green-400 text-sm font-bold">12 New This Week</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              { name: "PMEGP Manufacturing", state: "Central", val: "Up to ₹50L", tag: "Subsidy" },
              { name: "PM FME Food Units", state: "Central", val: "35% Grant", tag: "Food Tech" },
              { name: "MSME Idea Hackathon", state: "Central", val: "₹15L Equity-Free", tag: "Startup" },
              { name: "Karnataka Elevate", state: "Karnataka", val: "Grant-in-Aid", tag: "Innovation" },
              { name: "CM-EGP Scheme", state: "Maharashtra", val: "15-35% Subsidy", tag: "New Unit" },
              { name: "Startup India Seed Fund", state: "Central", val: "₹20L - ₹50L", tag: "Seed" }
            ].map((s, i) => (
              <div key={s.name} className="p-8 glass rounded-[2.5rem] border border-white/5 hover:border-blue-500/20 transition-all group">
                <div className="flex justify-between items-start mb-6">
                  <div className="px-3 py-1 bg-blue-500/10 rounded-lg text-blue-500 text-[10px] font-black uppercase tracking-widest">{s.state}</div>
                  <div className="text-slate-500"><Lock size={16} /></div>
                </div>
                <h4 className="text-xl font-black text-white mb-4 group-hover:text-blue-400 transition-colors">{s.name}</h4>
                <div className="flex justify-between items-center mt-8">
                  <div className="text-blue-500 font-black text-lg">{s.val}</div>
                  <div className="text-slate-500 text-xs font-bold">{s.tag}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-40 px-6 text-center">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-5xl md:text-8xl font-black text-white mb-10 tracking-tighter">
            Don't leave money <br /> on the table.
          </h2>
          <p className="text-xl md:text-2xl text-slate-500 mb-16 max-w-2xl mx-auto">
            Take 5 minutes today. Secure your business's future for tomorrow.
          </p>
          <Link href="/register" className="inline-flex items-center px-12 py-6 bg-white text-slate-900 text-2xl font-black rounded-[2rem] hover:scale-105 hover:bg-blue-500 hover:text-white transition-all shadow-2xl">
            Register & Discover
            <ArrowRight className="ml-3" />
          </Link>
        </div>
      </section>

      {/* Footer - Professional Multi-column */}
      <footer className="py-24 px-6 md:px-12 border-t border-white/5 bg-slate-950/50">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-16 mb-20">
          <div className="col-span-1 md:col-span-1">
            <div className="flex items-center space-x-2 mb-8">
              <Shield className="text-blue-500 w-6 h-6" />
              <span className="font-outfit font-black text-2xl text-white">GovGrant</span>
            </div>
            <p className="text-slate-500 text-sm leading-relaxed">
              Empowering the next generation of Indian entrepreneurs through AI-driven grant accessibility.
            </p>
          </div>

          <div>
            <h5 className="text-white font-black text-xs tracking-widest uppercase mb-8">Platform</h5>
            <ul className="space-y-4 text-slate-500 text-sm font-bold">
              <li><Link href="/chat" className="hover:text-blue-500 transition-colors">Find Grants</Link></li>
              <li><Link href="/results" className="hover:text-blue-500 transition-colors">Sample Reports</Link></li>
              <li><Link href="/pricing" className="hover:text-blue-500 transition-colors">Pricing</Link></li>
            </ul>
          </div>

          <div>
            <h5 className="text-white font-black text-xs tracking-widest uppercase mb-8">Resources</h5>
            <ul className="space-y-4 text-slate-500 text-sm font-bold">
              <li><Link href="#" className="hover:text-blue-500 transition-colors">Grant Guide</Link></li>
              <li><Link href="#" className="hover:text-blue-500 transition-colors">MSME FAQ</Link></li>
              <li><Link href="#" className="hover:text-blue-500 transition-colors">Portal Links</Link></li>
            </ul>
          </div>

          <div>
            <h5 className="text-white font-black text-xs tracking-widest uppercase mb-8">Company</h5>
            <ul className="space-y-4 text-slate-500 text-sm font-bold">
              <li><Link href="#" className="hover:text-blue-500 transition-colors">About Us</Link></li>
              <li><Link href="#" className="hover:text-blue-500 transition-colors">Privacy Policy</Link></li>
              <li><Link href="#" className="hover:text-blue-500 transition-colors">Contact</Link></li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto pt-12 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-6">
          <p className="text-slate-600 text-xs font-bold uppercase tracking-widest">
            © 2024 GovGrant AI Solutions. All rights reserved.
          </p>
          <div className="flex space-x-8 text-slate-600">
            <Globe className="hover:text-white transition-colors cursor-pointer" size={20} />
            <TrendingUp className="hover:text-white transition-colors cursor-pointer" size={20} />
            <Lock className="hover:text-white transition-colors cursor-pointer" size={20} />
          </div>
        </div>
      </footer>
    </div>
  );
}
