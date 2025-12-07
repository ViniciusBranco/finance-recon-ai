import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { uploadDocument } from '../lib/api';
import clsx from 'clsx';

export const UploadZone: React.FC = () => {
    const [uploading, setUploading] = useState(false);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
    const [message, setMessage] = useState<string | null>(null);

    const onDrop = useCallback(async (acceptedFiles: File[]) => {
        if (acceptedFiles.length === 0) return;

        setUploading(true);
        setUploadStatus('idle');
        setMessage(null);

        try {
            // Upload files sequentially
            for (const file of acceptedFiles) {
                await uploadDocument(file);
            }

            setUploadStatus('success');
            setMessage(`Successfully uploaded ${acceptedFiles.length} file(s).`);
        } catch (error) {
            console.error(error);
            setUploadStatus('error');
            setMessage('Failed to upload documents. Please try again.');
        } finally {
            setUploading(false);
            // Reset status after a delay
            setTimeout(() => setUploadStatus('idle'), 5000);
        }
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

    return (
        <div
            {...getRootProps()}
            className={clsx(
                "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors duration-200 ease-in-out",
                isDragActive ? "border-blue-500 bg-blue-50/10" : "border-slate-300 hover:border-blue-400 hover:bg-slate-50/5",
                "flex flex-col items-center justify-center gap-4 h-64 w-full max-w-2xl mx-auto dark:border-slate-700 dark:hover:bg-slate-900",
                uploadStatus === 'error' && "border-red-300 bg-red-50/10 dark:border-red-900/50",
                uploadStatus === 'success' && "border-green-300 bg-green-50/10 dark:border-green-900/50"
            )}
        >
            <input {...getInputProps()} />

            {uploading ? (
                <div className="flex flex-col items-center animate-pulse">
                    <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
                    <p className="mt-2 text-slate-500 font-medium">Uploading & Processing...</p>
                </div>
            ) : uploadStatus === 'success' ? (
                <div className="flex flex-col items-center text-green-600 dark:text-green-400">
                    <CheckCircle className="w-12 h-12 mb-2" />
                    <p className="font-semibold text-lg">Upload Complete!</p>
                    {message && <p className="text-sm opacity-90">{message}</p>}
                </div>
            ) : uploadStatus === 'error' ? (
                <div className="flex flex-col items-center text-red-500 dark:text-red-400">
                    <AlertCircle className="w-12 h-12 mb-2" />
                    <p className="font-semibold text-lg">Upload Failed</p>
                    {message && <p className="text-sm opacity-90">{message}</p>}
                </div>
            ) : (
                <>
                    <div className="p-4 rounded-full bg-slate-100 dark:bg-slate-800">
                        <Upload className="w-8 h-8 text-slate-400" />
                    </div>
                    <div className="space-y-1">
                        <p className="text-lg font-medium text-slate-700 dark:text-slate-200">
                            {isDragActive ? "Drop the files here..." : "Click to upload or drag and drop"}
                        </p>
                        <p className="text-sm text-slate-500">
                            PDF, Excel, CSV (max 10MB)
                        </p>
                    </div>
                </>
            )}
        </div>
    );
};
