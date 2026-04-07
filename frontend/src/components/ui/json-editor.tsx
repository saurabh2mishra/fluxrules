import Editor, { type OnMount } from '@monaco-editor/react';
import { useDarkMode } from '../../hooks/useDarkMode';
import { useRef } from 'react';

interface JsonEditorProps {
    value: string;
    onChange?: (value: string) => void;
    height?: string;
    readOnly?: boolean;
    language?: string;
}

export function JsonEditor({
    value,
    onChange,
    height = '300px',
    readOnly = false,
    language = 'json',
}: JsonEditorProps) {
    const { dark } = useDarkMode();
    const editorRef = useRef<unknown>(null);

    const handleMount: OnMount = (editor) => {
        editorRef.current = editor;
    };

    return (
        <div className="border border-border/60 rounded-xl overflow-hidden shadow-sm">
            <Editor
                height={height}
                language={language}
                theme={dark ? 'vs-dark' : 'light'}
                value={value}
                onChange={(val) => onChange?.(val ?? '')}
                onMount={handleMount}
                options={{
                    readOnly,
                    minimap: { enabled: false },
                    fontSize: 13,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    tabSize: 2,
                    automaticLayout: true,
                    formatOnPaste: true,
                    renderLineHighlight: 'line',
                    padding: { top: 8, bottom: 8 },
                }}
            />
        </div>
    );
}
