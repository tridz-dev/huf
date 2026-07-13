import { db } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import { doctype } from '@/data/doctypes';

export interface SSHConnectionDoc {
	name: string;
	display_name: string;
	host: string;
	port?: number;
	username: string;
	enabled: 0 | 1;
	auth_method: 'Password' | 'Private Key';
	host_key_verification?: string;
	host_key_fingerprint?: string;
	host_key_type?: string;
	host_key_enrolled_by?: string;
	host_key_enrolled_on?: string;
	last_tested_on?: string;
	last_test_status?: string;
	key_rotated_on?: string;
	last_error?: string;
}

export interface SSHConnectionRef {
	name?: string;
	ssh_connection: string;
	display_name?: string;
	host?: string;
	port?: number;
	username?: string;
	enabled?: boolean | number;
	last_test_status?: string;
}

export async function getSSHConnections(): Promise<SSHConnectionDoc[]> {
	try {
		const response = await db.getDocList(doctype['SSH Connection'], {
			fields: [
				'name',
				'display_name',
				'host',
				'port',
				'username',
				'enabled',
				'auth_method',
				'host_key_verification',
				'host_key_fingerprint',
				'host_key_type',
				'host_key_enrolled_by',
				'host_key_enrolled_on',
				'last_tested_on',
				'last_test_status',
				'key_rotated_on',
				'last_error',
			],
			orderBy: { field: 'display_name', order: 'asc' },
			limit: 200,
		});
		return response as SSHConnectionDoc[];
	} catch (error) {
		handleFrappeError(error, 'Error fetching SSH connections');
		throw error;
	}
}

export async function getSSHConnection(name: string): Promise<SSHConnectionDoc> {
	try {
		const response = await db.getDoc(doctype['SSH Connection'], name);
		return response as SSHConnectionDoc;
	} catch (error) {
		handleFrappeError(error, `Error fetching SSH connection ${name}`);
		throw error;
	}
}
