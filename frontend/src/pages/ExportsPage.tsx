import { Download } from 'lucide-react'
import { Button, Card, CardHeader, PageHeader } from '../components/ui'

export function ExportsPage() {
  return <div>
    <PageHeader title="Exports" subtitle="Download Personal and Work transactions as separate CSV files" />
    <div className="grid gap-4 md:grid-cols-2">
      <Card padding="md"><CardHeader title="Personal transactions" subtitle="Only rows sorted as Personal" /><Button leftIcon={<Download className="size-4" />}><a href="/api/v1/transactions/export/personal" className="text-inherit no-underline">Download Personal CSV</a></Button></Card>
      <Card padding="md"><CardHeader title="Work transactions" subtitle="Only rows sorted as Work" /><Button leftIcon={<Download className="size-4" />}><a href="/api/v1/transactions/export/work" className="text-inherit no-underline">Download Work CSV</a></Button></Card>
    </div>
  </div>
}
