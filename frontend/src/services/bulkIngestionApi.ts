import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

// ---------------------------------------------------------------------------
// Bulk Ingestion
// ---------------------------------------------------------------------------

export interface IngestionJobItemSummary {
  external_path: string;
  status: string;
  error_message?: string;
}

export interface IngestionJobProgress {
  status: string;
  total_discovered: number;
  pending: number;
  processing: number;
  succeeded: number;
  failed: number;
  skipped: number;
  error_message?: string;
  items: IngestionJobItemSummary[];
}

export async function startUploadImport(
  knowledgeSource: string,
  fileUrls: string[],
): Promise<{ ingestion_job: string }> {
  try {
    const result = await call.post(
      'huf.ai.knowledge.bulk.api.start_upload_import',
      { knowledge_source: knowledgeSource, files: JSON.stringify(fileUrls) },
    );
    const response = result as { message?: { ingestion_job: string } } & {
      ingestion_job: string;
    };
    return response.message ?? response;
  } catch (error) {
    handleFrappeError(error, 'Error starting upload import');
  }
}

export async function startDirectoryImport(
  knowledgeSource: string,
  directoryPath: string,
): Promise<{ ingestion_job: string }> {
  try {
    const result = await call.post(
      'huf.ai.knowledge.bulk.api.start_directory_import',
      { knowledge_source: knowledgeSource, directory_path: directoryPath },
    );
    const response = result as { message?: { ingestion_job: string } } & {
      ingestion_job: string;
    };
    return response.message ?? response;
  } catch (error) {
    handleFrappeError(error, 'Error starting directory import');
  }
}

export async function startS3Import(
  knowledgeSource: string,
  bucket: string,
  prefix?: string,
): Promise<{ ingestion_job: string }> {
  try {
    const result = await call.post(
      'huf.ai.knowledge.bulk.api.start_s3_import',
      { knowledge_source: knowledgeSource, bucket, prefix: prefix ?? '' },
    );
    const response = result as { message?: { ingestion_job: string } } & {
      ingestion_job: string;
    };
    return response.message ?? response;
  } catch (error) {
    handleFrappeError(error, 'Error starting S3 import');
  }
}

export async function startSftpImport(
  knowledgeSource: string,
  sftpConnection: string,
  rootPath: string,
): Promise<{ ingestion_job: string }> {
  try {
    const result = await call.post(
      'huf.ai.knowledge.bulk.api.start_sftp_import',
      {
        knowledge_source: knowledgeSource,
        sftp_connection: sftpConnection,
        root_path: rootPath,
      },
    );
    const response = result as { message?: { ingestion_job: string } } & {
      ingestion_job: string;
    };
    return response.message ?? response;
  } catch (error) {
    handleFrappeError(error, 'Error starting SFTP import');
  }
}

export async function getJobProgress(jobName: string): Promise<IngestionJobProgress> {
  try {
    const result = await call.get(
      'huf.ai.knowledge.bulk.api.get_job_progress',
      { ingestion_job: jobName },
    );
    const response = result as { message?: IngestionJobProgress } | undefined;
    return (response?.message ?? response) as IngestionJobProgress;
  } catch (error) {
    handleFrappeError(error, 'Error fetching ingestion job progress');
  }
}
