
from odoo import models, api
from datetime import datetime, date




class ReportAccountWizard(models.AbstractModel):
    _name = "report.multi_branch_management_aagam.pdf_cash_flow_report"

    @api.model
    def _get_report_values(self, docids, data=None):
        all_data_get = []
        move_data = []
        journal_data_get = []
        fetch_data = []
        active_model = self.env.context.get('active_model')
        docs = self.env[self.env.context.get('active_model')].browse(
            self.env.context.get('active_id'))
        branch_id = data['branch_id']
        if data['levels'] == 'summary' and data['report_period'] == 'datewise':
            state = """ WHERE am.state = 'posted' """ if data[
                                                             'target_move'] == 'posted' else ''
            query3 = """SELECT to_char(am.date, 'Month') as month_part, extract(
                   YEAR from am.date) as year_part,aml.branch_id AS branch , aml.company_id AS company,
                   sum(aml.debit) AS total_debit, sum(aml.credit) AS total_credit,sum(aml.balance) AS total_balance FROM(
                   SELECT am.date, am.id, am.state FROM account_move as am
                            LEFT JOIN account_move_line aml ON aml.move_id = am.id
                            LEFT JOIN account_account aa ON aa.id = aml.account_id
                            WHERE am.date BETWEEN '""" + str(
                data['date_from']) + """' and '""" + str(
                data['date_to']) + """' ) am
                            LEFT JOIN account_move_line aml ON aml.move_id = am.id
                            LEFT JOIN account_account aa ON aa.id = aml.account_id 
                            """ + state + """ AND aml.branch_id = """ + str(branch_id) + """ GROUP BY month_part,year_part,branch,company"""
            cr = self._cr
            cr.execute(query3)
            all_data_get = cr.dictfetchall()
        elif data['levels'] == 'summary' and data['report_period'] == 'yearly':
            now = datetime.now()
            last_year = now.year - data['previous_period']
            start_date = f'{last_year} {now.month} {now.day}'
            start_date_object = datetime.strptime(start_date, "%Y %m %d").date()
            state = """ WHERE am.state = 'posted' """ if data[
                                                             'target_move'] == 'posted' else ''
            query3 = """SELECT to_char(am.date, 'Month') as month_part, extract(
                   YEAR from am.date) as year_part,aml.branch_id AS branch , aml.company_id AS company,
                   sum(aml.debit) AS total_debit, sum(aml.credit) AS total_credit,sum(aml.balance) AS total_balance FROM(
                   SELECT am.date, am.id, am.state FROM account_move as am
                            LEFT JOIN account_move_line aml ON aml.move_id = am.id
                            LEFT JOIN account_account aa ON aa.id = aml.account_id
                            WHERE am.date BETWEEN '""" + str(
                start_date_object) + """' and '""" + str(
                data['date_to']) + """' ) am
                            LEFT JOIN account_move_line aml ON aml.move_id = am.id
                            LEFT JOIN account_account aa ON aa.id = aml.account_id

                            """ + state + """ AND aml.branch_id = """ + str(
                branch_id) + """ GROUP BY month_part,year_part,branch,company"""
            cr = self._cr
            cr.execute(query3)
            all_data_get = cr.dictfetchall()

        elif data['levels'] == 'consolidated' and data['report_period'] == 'datewise':
            state = """ WHERE am.state = 'posted' """ if data[
                                             'target_move'] == 'posted' else ''
            query2 = """SELECT aa.name, sum(aml.debit) AS total_debit, sum(
            aml.credit) AS total_credit,sum(aml.balance) AS total_balance ,aml.branch_id AS branch , aml.company_id AS company FROM(
                 SELECT am.id, am.state FROM account_move as am
                 LEFT JOIN account_move_line aml ON aml.move_id = am.id
                 LEFT JOIN account_account aa ON aa.id = aml.account_id
                 WHERE am.date BETWEEN '""" + str(
                 data['date_from']) + """' and '""" + str(
                 data['date_to']) + """' ) am
                 LEFT JOIN account_move_line aml ON aml.move_id = am.id
                 LEFT JOIN account_account aa ON aa.id = aml.account_id
                 """ + state + """AND aml.branch_id = """ + str(branch_id) + """ GROUP BY aa.name,company,branch"""
            cr = self._cr
            cr.execute(query2)
            all_data_get = cr.dictfetchall()
        elif data['levels'] == 'consolidated' and data['report_period'] == 'yearly':
            now = datetime.now()
            last_year = now.year - data['previous_period']
            start_date = f'{last_year} {now.month} {now.day}'
            start_date_object = datetime.strptime(start_date, "%Y %m %d").date()
            state = """ WHERE am.state = 'posted' """ if data[
                                                             'target_move'] == 'posted' else ''
            query2 = """SELECT aa.name, sum(aml.debit) AS total_debit, sum(
                        aml.credit) AS total_credit,sum(aml.balance) AS total_balance ,aml.branch_id AS branch , aml.company_id AS company FROM(
                             SELECT am.id, am.state FROM account_move as am
                             LEFT JOIN account_move_line aml ON aml.move_id = am.id
                             LEFT JOIN account_account aa ON aa.id = aml.account_id
                             WHERE am.date BETWEEN '""" + str(
                start_date_object) + """' and '""" + str(
                data['date_to']) + """' ) am
                             LEFT JOIN account_move_line aml ON aml.move_id = am.id
                             LEFT JOIN account_account aa ON aa.id = aml.account_id
                             """ + state + """AND aml.branch_id = """ + str(
                branch_id) + """ GROUP BY aa.name,company,branch"""
            cr = self._cr
            cr.execute(query2)
            all_data_get = cr.dictfetchall()
        elif data['levels'] == 'detailed' and data['report_period'] == 'datewise':
            state = """ WHERE am.state = 'posted' """ if data[
                                         'target_move'] == 'posted' else ''
            query1 = """SELECT aa.name,aa.code, sum(
                    aml.debit) AS total_debit, sum(aml.credit) AS total_credit,
                         sum(aml.balance) AS total_balance ,aml.branch_id AS branch , aml.company_id AS company FROM (
                         SELECT am.id, am.state FROM account_move as am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                         WHERE am.date BETWEEN '""" + str(
                            data['date_from']) + """' and '""" + str(
                            data['date_to']) + """' ) am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                          
                         """ + state + """AND aml.branch_id = """ + str(branch_id) + """ GROUP BY aa.name, aa.code,branch,company"""
            cr = self._cr
            cr.execute(query1)
            all_data_get = cr.dictfetchall()
            for account in self.env['account.account'].search([]):
                child_lines = self._get_journal_lines(account, data)
                if child_lines:
                    journal_data_get.append(child_lines)
        elif data['levels'] == 'detailed' and data['report_period'] == 'yearly':
            now = datetime.now()
            last_year = now.year - data['previous_period']
            start_date = f'{last_year} {now.month} {now.day}'
            start_date_object = datetime.strptime(start_date, "%Y %m %d").date()
            state = """ WHERE am.state = 'posted' """ if data[
                                                             'target_move'] == 'posted' else ''
            query1 = """SELECT aa.name,aa.code, sum(
                                aml.debit) AS total_debit, sum(aml.credit) AS total_credit,
                                     sum(aml.balance) AS total_balance ,aml.branch_id AS branch , aml.company_id AS company FROM (
                                     SELECT am.id, am.state FROM account_move as am
                                     LEFT JOIN account_move_line aml ON aml.move_id = am.id
                                     LEFT JOIN account_account aa ON aa.id = aml.account_id
                                     WHERE am.date BETWEEN '""" + str(
                start_date_object) + """' and '""" + str(
                data['date_to']) + """' ) am
                                     LEFT JOIN account_move_line aml ON aml.move_id = am.id
                                     LEFT JOIN account_account aa ON aa.id = aml.account_id

                                     """ + state + """AND aml.branch_id = """ + str(
                branch_id) + """ GROUP BY aa.name, aa.code,branch,company"""
            cr = self._cr
            cr.execute(query1)
            all_data_get = cr.dictfetchall()
            for account in self.env['account.account'].search([]):
                child_lines = self._get_journal_lines(account, data)
                if child_lines:
                    journal_data_get.append(child_lines)
        elif data['levels'] == 'very' and data['report_period'] == 'datewise':
            state = """AND am.state = 'posted' """ if data[
                                          'target_move'] == 'posted' else ''
            sql = """SELECT DISTINCT aa.name,aa.code, sum(
            aml.debit) AS total_debit,
                         sum(aml.credit) AS total_credit ,aml.branch_id AS branch , aml.company_id AS company FROM (
                         SELECT am.* FROM account_move as am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                         WHERE am.date BETWEEN '""" + str(
                data['date_from']) + """' and '""" + str(
                data['date_to']) + """'  """ + state + """) am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                          WHERE aml.branch_id = """ + str(branch_id) + """
                         GROUP BY aa.name, aa.code,branch,company"""
            cr = self._cr
            cr.execute(sql)
            fetch_data = cr.dictfetchall()
            for account in self.env['account.account'].search([]):
                child_lines = self._get_lines(account, data)
                if child_lines:
                    move_data.append(child_lines)
        elif data['levels'] == 'very' and data['report_period'] == 'yearly':
            now = datetime.now()
            last_year = now.year - data['previous_period']
            start_date = f'{last_year} {now.month} {now.day}'
            start_date_object = datetime.strptime(start_date, "%Y %m %d").date()
            state = """AND am.state = 'posted' """ if data[
                                                          'target_move'] == 'posted' else ''
            sql = """SELECT DISTINCT aa.name,aa.code, sum(
                       aml.debit) AS total_debit,
                                    sum(aml.credit) AS total_credit ,aml.branch_id AS branch , aml.company_id AS company FROM (
                                    SELECT am.* FROM account_move as am
                                    LEFT JOIN account_move_line aml ON aml.move_id = am.id
                                    LEFT JOIN account_account aa ON aa.id = aml.account_id
                                    WHERE am.date BETWEEN '""" + str(
                start_date_object) + """' and '""" + str(
                data['date_to']) + """'  """ + state + """) am
                                    LEFT JOIN account_move_line aml ON aml.move_id = am.id
                                    LEFT JOIN account_account aa ON aa.id = aml.account_id
                                     WHERE aml.branch_id = """ + str(branch_id) + """
                                    GROUP BY aa.name, aa.code,branch,company"""
            cr = self._cr
            cr.execute(sql)
            fetch_data = cr.dictfetchall()
            for account in self.env['account.account'].search([]):
                child_lines = self._get_lines(account, data)
                if child_lines:
                    move_data.append(child_lines)

        return {
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'levels': data['levels'],
            'doc_ids': self.ids,
            'doc_model': active_model,
            'docs': docs,
            'all_data_get': all_data_get,
            'move_data': move_data,
            'journal_data_get': journal_data_get,
            'fetch_data': fetch_data,
        }

    def _get_lines(self, account, data):
        state = """AND am.state = 'posted' """ if data[
                                          'target_move'] == 'posted' else ''
        query = """SELECT aml.account_id,aj.name, am.name as move_name, sum(
        aml.debit) AS total_debit, 
             sum(aml.credit) AS total_credit FROM (
             SELECT am.* FROM account_move as am
             LEFT JOIN account_move_line aml ON aml.move_id = am.id
             LEFT JOIN account_account aa ON aa.id = aml.account_id
             WHERE am.date BETWEEN '""" + str(
            data['date_from']) + """' and '""" + str(
            data['date_to']) + """' """ + state + """) am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                         LEFT JOIN account_journal aj ON aj.id = am.journal_id
                         WHERE aa.id = """ + str(account.id) + """
                         GROUP BY am.name, aml.account_id, aj.name"""

        cr = self._cr
        cr.execute(query)
        all_data_get = cr.dictfetchall()
        sql2 = """SELECT aa.name as account_name, aj.id, aj.name, sum(
        aml.debit) AS total_debit,
                 sum(aml.credit) AS total_credit FROM (
                 SELECT am.* FROM account_move as am
                     LEFT JOIN account_move_line aml ON aml.move_id = am.id
                     LEFT JOIN account_account aa ON aa.id = aml.account_id
                     WHERE am.date BETWEEN '""" + str(
            data['date_from']) + """' and '""" + str(
            data['date_to']) + """' """ + state + """) am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                         LEFT JOIN account_journal aj ON aj.id = am.journal_id
                         WHERE aa.id = """ + str(account.id) + """
                         GROUP BY aa.name, aj.name, aj.id"""
        cr = self._cr
        cr.execute(sql2)
        fetch_data = cr.dictfetchall()
        if all_data_get:
            return {
                'account': account.name,
                'code': account.code,
                'move_lines': all_data_get,
                'journal_lines': fetch_data,
            }

    def _get_journal_lines(self, account, data):
        state = """AND am.state = 'posted' """ if data[
                                          'target_move'] == 'posted' else ''
        sql2 = """SELECT aa.name as account_name, aj.id, aj.name, sum(
        aml.debit) AS total_debit,
         sum(aml.credit) AS total_credit FROM (
         SELECT am.* FROM account_move as am
             LEFT JOIN account_move_line aml ON aml.move_id = am.id
             LEFT JOIN account_account aa ON aa.id = aml.account_id
             WHERE am.date BETWEEN '""" + str(
            data['date_from']) + """' and '""" + str(
            data['date_to']) + """'  """ + state + """) am
                         LEFT JOIN account_move_line aml ON aml.move_id = am.id
                         LEFT JOIN account_account aa ON aa.id = aml.account_id
                         LEFT JOIN account_journal aj ON aj.id = am.journal_id
                         WHERE aa.id = """ + str(account.id) + """
                         GROUP BY aa.name, aj.name, aj.id"""
        cr = self._cr
        cr.execute(sql2)
        all_data_get = cr.dictfetchall()
        if all_data_get:
            return {
                'account': account.name,
                'journal_lines': all_data_get,
            }
