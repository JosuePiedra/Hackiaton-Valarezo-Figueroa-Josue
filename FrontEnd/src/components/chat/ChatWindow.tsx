import React, { useState, useRef, useEffect } from 'react';
import { RotateCcw, MessageSquare } from 'lucide-react';
import { ChatMessage, type MessageProps } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { ExamplePrompts } from './ExamplePrompts';
import { sendInsuranceChatMessage } from '../../api/insuranceApi';
import { getOrCreateSessionId, resetSessionId } from '../../utils/session';

export const ChatWindow: React.FC = () => {
  const [messages, setMessages] = useState<MessageProps[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async (content: string) => {
    const userMsg: MessageProps = { id: Date.now().toString(), isUser: true, content };
    setMessages(prev => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const sessionId = getOrCreateSessionId();
      const res = await sendInsuranceChatMessage(content, sessionId);

      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        isUser: false,
        content: res.reply,
        response_type: res.response_type,
        plans: res.plans,
        specialty: res.specialty,
        estimated_copay: res.estimated_copay,
        requires_authorization: res.requires_authorization,
        waiting_period_days: res.waiting_period_days,
        network_tier: res.network_tier,
        providers: res.providers,
        annual_deductible: res.annual_deductible,
        notes: res.notes,
        deductible_applies: res.deductible_applies,
      }]);
    } catch {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        isUser: false,
        content: 'No pude consultar la cobertura en este momento. Intenta nuevamente.',
        response_type: 'general',
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    resetSessionId();
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-full w-full bg-white rounded-2xl border border-slate-200 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
        <span className="text-xs text-slate-400">
          Estimación informativa · No reemplaza confirmación oficial de la aseguradora
        </span>
        {messages.length > 0 && (
          <button
            onClick={handleReset}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-700 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Nueva consulta
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center px-6 py-12 text-center">
            <div className="w-12 h-12 bg-blue-50 rounded-2xl flex items-center justify-center mb-5">
              <MessageSquare className="w-6 h-6 text-blue-500" />
            </div>
            <h3 className="text-base font-semibold text-slate-800 mb-1">¿En qué te puedo ayudar?</h3>
            <p className="text-sm text-slate-400 mb-7 max-w-xs">
              Cuéntame tu consulta médica y tu plan de seguro para estimar cobertura y copago.
            </p>
            <ExamplePrompts onSelect={handleSend} disabled={isLoading} />
          </div>
        ) : (
          <div className="py-2">
            {messages.map(msg => (
              <ChatMessage
                key={msg.id}
                {...msg}
                onPlanSelect={isLoading ? undefined : handleSend}
              />
            ))}
            {isLoading && (
              <ChatMessage id="loading" isUser={false} content="" isLoading />
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-slate-100 bg-white">
        <ChatInput onSend={handleSend} isLoading={isLoading} />
      </div>
    </div>
  );
};
